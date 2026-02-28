import asyncio
import aiohttp
import sys
import os

from dotenv import load_dotenv

# Appending to sys.path so we can import src module safely.
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from poly_trade import place_order

load_dotenv()

async def fetch_test_token():
    """Fetch an active market token from the CLOB directly to perform a safe limit order test."""
    url = f"https://clob.polymarket.com/markets"
    
    async with aiohttp.ClientSession() as session:
        print("Fetching a single active market from the CLOB matching engine...")
        cursor = ""
        while True:
            params = {"next_cursor": cursor} if cursor else {}
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                markets = data.get('data', [])
                if not markets:
                    print("Could not fetch any CLOB markets.")
                    return None
                
                for market in markets:
                    # Look for heavily traded active markets
                    if not market.get("closed") and market.get("active"):
                        tokens = market.get('tokens', [])
                        if tokens and len(tokens) >= 2:
                            raw_token_id = str(tokens[0].get("token_id"))
                            print(f"Found active CLOB market: {market.get('question')}")
                            print(f"Testing Trade on YES token ID: {raw_token_id}")
                            return raw_token_id
                            
                cursor = data.get('next_cursor')
                if not cursor or cursor == "LTE=":
                    break
        return None

async def main():
    print("=== POLYMARKET ARBITRAGE TEST TRADE ===")
    
    if not os.getenv("POLYMARKET_APIKEY"):
        print("ERROR: POLYMARKET_APIKEY not found in .env")
        return
        
    token_id = await fetch_test_token()
    if not token_id:
        print("Could not retrieve a valid token ID. Aborting.")
        return
        
    print("\nAttempting to place a test limit BUY order using Good Till Canceled (GTC).")
    print("Price is set to 1c so it almost certainly will NOT execute.")
    print("This just validates that the API authentication and order signing process works correctly.\n")
    
    # We use a very low limit buy price (1 cent) so it rests on the book and won't match immediately.
    # We also use GTC so it is accepted by the CLOB resting matcher.
    resp = await place_order(
        token_id=token_id,
        action="buy",
        count=1, # min 5
        price_cents=1,  # 1c limit order! VERY SAFE.
        order_type="good_till_canceled"
    )
    
    if resp and resp.get("success"):
        print("\n✅ API KEY IS VALID AND ORDER CREATION IS SUCCESSFUL!")
        print("Response:", resp)
        print("\n🚨 Please navigate to your Polymarket portfolio and CANCEL this test 1c limit order if you wish.")
    else:
        print("\n❌ API REJECTED THE ORDER.")
        if resp:
            print(f"Error Message: {resp.get('errorMsg')}")

if __name__ == "__main__":
    asyncio.run(main())
