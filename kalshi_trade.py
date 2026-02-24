import aiohttp
import uuid
import logging
import os
from kalshi_auth import get_auth_headers
from desktop_notifier import DesktopNotifier

logger = logging.getLogger(__name__)
notifier = DesktopNotifier()

async def place_order(ticker: str, action: str, side: str, count: int, yes_price: int, no_price: int, order_type: str = "immediate_or_cancel") -> dict | None:
    """
    Places an order on Kalshi v2 API.
    
    Args:
        ticker: The market ticker, e.g., 'KXBTC-24DEC31'
        action: 'buy' or 'sell'
        side: 'yes' or 'no'
        count: Number of contracts
        yes_price: The yes price in cents (1-99)
        no_price: The no price in cents (1-99), must satisfy yes_price + no_price = 100
        order_type: Available options: fill_or_kill, good_till_canceled, immediate_or_cancel 
    """
    url = "https://api.elections.kalshi.com/trade-api/v2/portfolio/orders"
    path = "/trade-api/v2/portfolio/orders"
    
    try:
        headers = get_auth_headers("POST", path)
    except ValueError as e:
        logger.error(f"Authentication error: {e}")
        return None
        
    headers["Content-Type"] = "application/json"
    
    client_order_id = str(uuid.uuid4())
    
    payload = {
        "action": action,
        "client_order_id": client_order_id,
        "count": count,
        "side": side,
        "ticker": ticker,
        "time_in_force": order_type
    }
    
    if side == "yes":
        payload["yes_price"] = yes_price
    else:
        payload["no_price"] = no_price

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if resp.status == 201 or resp.status == 200:
                    order_id = data.get('order', {}).get('order_id')
                    print(f"✅ Order placed successfully! ID: {order_id}")
                    try:
                        await notifier.send(
                            title="Kalshi Trade Executed",
                            message=f"Filled {count}x {side.upper()} on {ticker}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send notification: {e}")
                    
                    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
                    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
                    
                    if telegram_token and telegram_chat_id:
                        tg_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
                        tg_payload = {
                            "chat_id": telegram_chat_id, 
                            "text": f"✅ Kalshi Trade Executed\nFilled {count}x {side.upper()} on {ticker} for {yes_price if side == 'yes' else no_price}c"
                        }
                        try:
                            async with session.post(tg_url, json=tg_payload) as tg_resp:
                                if tg_resp.status != 200:
                                    logger.error(f"Failed to send Telegram notification: HTTP {tg_resp.status}")
                                else:
                                    print("📱 Sent Telegram notification.")
                        except Exception as e:
                            logger.error(f"Exception sending telegram notification: {e}")
                            
                    return data
                else:
                    print(f"❌ Failed to place order: HTTP {resp.status} - {data}")
                    return None
        except Exception as e:
            print(f"❌ Exception placing order: {e}")
            return None
