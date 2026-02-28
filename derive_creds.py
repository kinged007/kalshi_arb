import os
import asyncio
from dotenv import load_dotenv

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.constants import POLYGON
except ImportError:
    print("Please run this via: uv run python derive_creds.py")
    exit(1)

load_dotenv()

def main():
    print("=== POLYMARKET CLOB API CREDENTIAL DERIVATION ===")
    pk = os.getenv("POLYMARKET_PRIVATE_KEY")
    
    if not pk:
        print("❌ Error: Add your POLYMARKET_PRIVATE_KEY to the .env file first.")
        return

    print("Attempting to derive valid API credentials from the provided Private Key...")
    
    # Initialize without API Creds! Only the private key.
    # The client will use the private key to sign a request to Polymarket to generate its own API keys.
    client = ClobClient(
        "https://clob.polymarket.com",
        chain_id=POLYGON,
        key=pk 
    )
    
    try:
        # This makes an authenticated request to CLOB to register/derive the API keys for this wallet.
        creds = client.create_or_derive_api_creds()
        print("\n✅ Successfully Derived L2 API Credentials!")
        print("Please UPDATE your .env file with these 3 exact values:\n")
        print(f"POLYMARKET_APIKEY={creds.api_key}")
        print(f"POLYMARKET_SECRET={creds.api_secret}")
        print(f"POLYMARKET_PASSPHRASE={creds.api_passphrase}")
        print("\nOnce updated, re-run `uv run python test_trade.py`.")
        
    except Exception as e:
        print(f"\n❌ Failed to derive credentials: {e}")
        
if __name__ == "__main__":
    main()
