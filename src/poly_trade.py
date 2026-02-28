import os
import math
import time
import logging
import asyncio
from dotenv import load_dotenv
from desktop_notifier import DesktopNotifier
import aiohttp
from utils import notify_tg

load_dotenv()
logger = logging.getLogger(__name__)
notifier = DesktopNotifier()

# Substring present in the CLOB API errorMsg when a FAK order finds no matching liquidity
_FAK_NO_MATCH_MSG = "no orders found to match"

# Try to load py_clob_client
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType, PostOrdersArgs
    from py_clob_client.order_builder.constants import BUY, SELL
except ImportError:
    ClobClient = None
    logger.error("py_clob_client is not installed. Trading will not work.")

def get_clob_client() -> "ClobClient":
    if not ClobClient:
        raise ImportError("py_clob_client not installed")
        
    api_key = os.getenv("POLYMARKET_APIKEY")
    api_secret = os.getenv("POLYMARKET_SECRET")
    api_passphrase = os.getenv("POLYMARKET_PASSPHRASE")
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    
    if not all([api_key, api_secret, api_passphrase, private_key]):
        raise ValueError("Missing Polymarket credentials in .env (POLYMARKET_APIKEY, POLYMARKET_SECRET, POLYMARKET_PASSPHRASE, POLYMARKET_PRIVATE_KEY)")
        
    creds = ApiCreds(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase
    )
    
    # Initialize the client for Polygon mainnet
    from py_clob_client.constants import POLYGON
    
    # We pass the private key to the 'key' argument so the SDK can sign orders locally.
    client = ClobClient(
        "https://clob.polymarket.com",
        chain_id=POLYGON, 
        creds=creds,
        key=private_key,
        signature_type=1,
        funder=os.getenv("POLYMARKET_FUNDER_ADDRESS")
    )
    
    return client
async def place_order(token_id: str, action: str, count: int, price_cents: int, order_type: str = "immediate_or_cancel") -> dict | None:
    """
    Places an order on Polymarket CLOB via py-clob-client.
    
    Args:
        token_id: The specific ERC-1155 token ID for the asset/outcome.
        action: 'buy' or 'sell'
        count: Number of contracts (size)
        price_cents: The price in cents (1-99), will be converted to dollars (0.01 - 0.99)
        order_type: "immediate_or_cancel", "fill_or_kill", "good_till_canceled"
    """
    try:
        # To avoid blocking event loops with cryptography signing in py_clob_client, we run it in executor
        loop = asyncio.get_event_loop()
        
        # Convert price from cents to dollars
        price_dollars = price_cents / 100.0
        
        side = BUY if action.lower() == 'buy' else SELL
        
        clob_order_type = OrderType.FAK
        if order_type == "fill_or_kill":
            clob_order_type = OrderType.FOK
        elif order_type == "good_till_canceled":
            clob_order_type = OrderType.GTC
            
        # Create OrderArgs
        order_args = OrderArgs(
            price=price_dollars,
            size=count,
            side=side,
            token_id=token_id,
        )
        
        print(f"Signing {action.upper()} order for token {token_id[:8]}... at ${price_dollars} ({count} contracts)")
        
        def run_trade():
            client = get_clob_client()
            signed_order = client.create_order(order_args)
            return client.post_order(signed_order, clob_order_type)

        resp = await loop.run_in_executor(None, run_trade)
        
        if resp and resp.get("success"):
            order_id = resp.get("orderID")
            print(f"✅ Polymarket Order placed successfully! ID: {order_id}")
            
            msg = f"✅ Polymarket Trade Executed\nFilled {count}x {action.upper()} on token {token_id[:8]}... for {price_cents}c"
            
            try:
                await notifier.send(title="Polymarket Trade Executed", message=f"Filled {count}x {action.upper()} at {price_cents}c")
            except Exception as e:
                pass
                
            await notify_tg(msg)
            
            return resp
        else:
            print(f"❌ Failed to place Polymarket order: {resp}")
            return None
            
    except Exception as e:
        print(f"❌ Exception placing Polymarket order: {e}")
        return None


async def _fetch_best_ask_cents(token_id: str) -> int | None:
    """
    Fetch the current best ask price (in cents) for a token from the CLOB API.
    Uses get_price(side="BUY") which returns the cheapest available ask.
    """
    def fetch():
        client = get_clob_client()
        result = client.get_price(token_id, side="BUY")
        if result and "price" in result:
            return round(float(result["price"]) * 100)
        return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch)


async def place_arb_orders(
    yes_token_id: str,
    no_token_id: str,
    yes_price_cents: int,
    no_price_cents: int,
    count: int,
    order_type: str = "immediate_or_cancel",
) -> dict | None:
    """
    Places a YES and NO buy order atomically in a single batch call via
    py-clob-client's post_orders endpoint.

    Args:
        yes_token_id: ERC-1155 token ID for the YES outcome.
        no_token_id:  ERC-1155 token ID for the NO outcome.
        yes_price_cents: YES ask price in cents (1–99).
        no_price_cents:  NO ask price in cents (1–99).
        count: Number of contracts to buy on each side.
        order_type: "immediate_or_cancel", "fill_or_kill", or "good_till_canceled".

    Returns:
        The raw batch response dict from the CLOB API, or None on failure.
    """
    try:
        start_ts = time.time_ns()
        
        loop = asyncio.get_event_loop()

        yes_price = yes_price_cents / 100.0
        no_price = no_price_cents / 100.0

        # Polymarket enforces a $1 minimum order value (size × price >= $1).
        # Both legs must use the same count to preserve the arb guarantee.
        # Find the minimum count that satisfies the $1 floor for the cheaper side
        # (the more expensive side will automatically exceed $1 at that count),
        # then take the larger of that and the user-requested stake.
        POLY_MIN_ORDER_USD = 1.0
        min_count_for_arb = max(
            math.ceil(POLY_MIN_ORDER_USD / yes_price),
            math.ceil(POLY_MIN_ORDER_USD / no_price),
        )
        final_count = max(count, min_count_for_arb)

        if final_count != count:
            print(
                f"⚠️  Requested stake ({count}) is below Polymarket's ${POLY_MIN_ORDER_USD:.0f} minimum. "
                f"Adjusting both legs to {final_count} contracts."
            )

        clob_order_type = OrderType.FAK
        if order_type == "fill_or_kill":
            clob_order_type = OrderType.FOK
        elif order_type == "good_till_canceled":
            clob_order_type = OrderType.GTC

        print(
            f"Signing BATCH arb order — YES token {yes_token_id[:8]}... at ${yes_price:.2f}, "
            f"NO token {no_token_id[:8]}... at ${no_price:.2f} ({final_count} contracts each)"
        )

        def run_batch_trade():
            client = get_clob_client()

            yes_order = client.create_order(
                OrderArgs(price=yes_price, size=final_count, side=BUY, token_id=yes_token_id)
            )
            no_order = client.create_order(
                OrderArgs(price=no_price, size=final_count, side=BUY, token_id=no_token_id)
            )

            return client.post_orders([
                PostOrdersArgs(order=yes_order, orderType=clob_order_type),
                PostOrdersArgs(order=no_order,  orderType=clob_order_type),
            ])

        resp = await loop.run_in_executor(None, run_batch_trade)
        
        end_ts = time.time_ns()
        print(f"DEBUG: Batch order placed in {(end_ts - start_ts) / 1e6:.2f} ms")

        if not resp or not isinstance(resp, list):
            print(f"❌ Unexpected response from post_orders: {resp}")
            return None

        print(f"DEBUG: {resp}")

        # The API returns success=True even on failures — errorMsg is the only reliable signal.
        # Separate FAK-no-liquidity misses (retryable) from hard errors (not retryable).
        fak_misses: dict[int, tuple[str, str]] = {}  # leg_index -> (side_label, token_id)
        hard_errors: list[tuple[str, str]] = []       # list of (side_label, error_msg)

        for i, o in enumerate(resp):
            if not isinstance(o, dict):
                continue
            err = o.get("errorMsg", "")
            if not err:
                continue
            side = "YES" if i == 0 else "NO"
            if _FAK_NO_MATCH_MSG in err:
                fak_misses[i] = (side, yes_token_id if i == 0 else no_token_id)
            else:
                hard_errors.append((side, err))

        if hard_errors:
            for side, err in hard_errors:
                print(f"❌ Batch order error on {side} leg: {err}")
            return None

        async def _notify_success(act_yes_cents: int, act_no_cents: int, act_count: int) -> None:
            order_ids = [o.get("orderID", "") for o in resp if isinstance(o, dict) and o.get("orderID")]
            profit_per = 100 - act_yes_cents - act_no_cents
            print(f"✅ Polymarket arb position opened! IDs: {order_ids}")
            notification_msg = (
                f"✅ Polymarket Batch Arb Trade Executed\n"
                f"Bought {act_count}x YES at {act_yes_cents}c + {act_count}x NO at {act_no_cents}c\n"
                f"Locked profit: {profit_per}c/contract × {act_count} = {profit_per * act_count}c total"
            )
            try:
                await notifier.send(
                    title="Polymarket Arb Trade Executed",
                    message=f"YES {act_yes_cents}c + NO {act_no_cents}c × {act_count} contracts",
                )
            except Exception:
                pass
            await notify_tg(notification_msg)

        if not fak_misses:
            # Both legs filled on the first attempt.
            await _notify_success(yes_price_cents, no_price_cents, final_count)
            return resp

        # One or more legs missed on FAK (liquidity moved before the order landed).
        any_filled = any(
            isinstance(resp[i], dict) and not resp[i].get("errorMsg")
            for i in range(len(resp))
        )
        print(
            f"⚠️  {len(fak_misses)} leg(s) missed on FAK — price moved before order landed. "
            + ("One leg already filled — must retry to avoid unhedged exposure." if any_filled else "Fetching updated prices...")
        )

        # Fetch the current best ask for each failed leg.
        new_ask_cents: dict[int, int] = {}
        for idx, (side, token_id) in fak_misses.items():
            ask = await _fetch_best_ask_cents(token_id)
            if ask is None:
                unhedged_warn = " ⚠️  Unhedged position may exist!" if any_filled else ""
                print(f"❌ Could not fetch current {side} price.{unhedged_warn}")
                return None
            old = yes_price_cents if idx == 0 else no_price_cents
            print(f"  {side}: {old}c → {ask}c")
            new_ask_cents[idx] = ask

        # Use filled prices for successful legs, updated prices for missed legs.
        combined_yes = new_ask_cents.get(0, yes_price_cents)
        combined_no  = new_ask_cents.get(1, no_price_cents)
        combined_cost = combined_yes + combined_no

        if combined_cost >= 100:
            suffix = " — ⚠️  UNHEDGED POSITION MAY EXIST. Manual intervention required!" if any_filled else "."
            print(
                f"❌ Arb no longer valid at updated prices "
                f"(YES {combined_yes}c + NO {combined_no}c = {combined_cost}c){suffix}"
            )
            return None

        print(
            f"✅ Arb still valid at updated prices ({combined_yes}c + {combined_no}c = {combined_cost}c). "
            f"Retrying {len(fak_misses)} failed leg(s)..."
        )

        # Recalculate minimum count for the new prices before retrying.
        new_min_count = max(
            math.ceil(POLY_MIN_ORDER_USD / (combined_yes / 100)),
            math.ceil(POLY_MIN_ORDER_USD / (combined_no / 100)),
        )
        retry_count = max(final_count, new_min_count)

        for idx, (side, token_id) in fak_misses.items():
            new_price = new_ask_cents[idx]
            print(f"  Retrying {side} leg at {new_price}c × {retry_count} contracts...")
            result = await place_order(
                token_id=token_id,
                action="buy",
                count=retry_count,
                price_cents=new_price,
            )
            if not result:
                unhedged = " ⚠️  Unhedged position may exist!" if any_filled else ""
                print(f"❌ Retry failed on {side} leg.{unhedged}")
                return None

        await _notify_success(combined_yes, combined_no, retry_count)
        return resp

    except Exception as e:
        print(f"❌ Exception placing Polymarket batch arb order: {e}")
        return None
