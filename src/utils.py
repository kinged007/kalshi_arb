import os
import aiohttp
import logging

logger = logging.getLogger(__name__)

async def notify_tg(message: str) -> None:
    """
    Sends a message to the configured Telegram chat.
    Required environment variables: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    """
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if telegram_token and telegram_chat_id:
        tg_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        tg_payload = {
            "chat_id": telegram_chat_id, 
            "text": message
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(tg_url, json=tg_payload) as tg_resp:
                    if tg_resp.status != 200:
                        logger.error(f"Failed to send Telegram notification: HTTP {tg_resp.status}")
                    else:
                        print("📱 Sent Telegram notification.")
        except Exception as e:
            logger.error(f"Exception sending telegram notification: {e}")
