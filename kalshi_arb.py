import argparse
import asyncio
import aiohttp
import time
from dotenv import load_dotenv

from kalshi_ws import KalshiArbMonitor, NoActiveBidsException

load_dotenv()

async def search_markets(series_tickers_input: str):
    """Fetch series details and open markets for one or multiple series."""
    series_tickers = [s.strip().upper() for s in series_tickers_input.split(",") if s.strip()]
    
    async with aiohttp.ClientSession() as session:
        for series_ticker in series_tickers:
            url = f"https://api.elections.kalshi.com/trade-api/v2/series/{series_ticker}"
            print(f"Fetching series data for '{series_ticker}'...")
            
            # 1. Get Series Information
            async with session.get(url) as resp:
                data = await resp.json()
                if "error" in data:
                    print(f"Error fetching series '{series_ticker}': {data['error'].get('message', 'Unknown error')}\n")
                    continue
                
                series = data.get("series") or {}
                print("=" * 60)
                print(f"Series Title: {series.get('title')}")
                print(f"Category: {series.get('category')} | Frequency: {series.get('frequency')}")
                print("=" * 60)
                
            # 2. Get Open Markets for the Series
            markets_url = f"https://api.elections.kalshi.com/trade-api/v2/markets"
            params = {"series_ticker": series_ticker, "status": "open", "limit": 1000}
            
            async with session.get(markets_url, params=params) as resp:
                data = await resp.json()
                markets = data.get("markets", [])
                
                if not markets:
                    print("No open markets found for this series.\n")
                    continue
                
                # Group by Event Ticker
                events = {}
                for m in markets:
                    e_ticker = m.get("event_ticker", "Unknown Event")
                    if e_ticker not in events:
                        events[e_ticker] = []
                    events[e_ticker].append(m)
                    
                print(f"\nFound {len(markets)} active markets across {len(events)} events for {series_ticker}:\n")
                
                for event_ticker, event_markets in events.items():
                    print(f"--- Event: {event_ticker} ---")
                    for m in event_markets:
                        ticker = m.get('ticker')
                        title = m.get('title').encode('ascii', errors='replace').decode()
                        yes_ask = m.get("yes_ask", 0)
                        no_ask = m.get("no_ask", 0)
                        print(f"  [{ticker}] {title}")
                        print(f"    Yes Ask: {yes_ask}c | No Ask: {no_ask}c")
                    print()

def main():
    parser = argparse.ArgumentParser(description="Kalshi Arbitrage Monitor Phase 1")
    subparsers = parser.add_subparsers(dest="command", help="Command to run", required=True)
    
    # Subparser for search
    parser_search = subparsers.add_parser("search", help="Search for active markets")
    parser_search.add_argument("series_ticker", type=str, help="Series Ticker (e.g., 'KXBTC', 'KXHIGHNY')")
    
    # Subparser for watch
    parser_watch = subparsers.add_parser("watch", help="Watch specific series or tags for arbitrage")
    parser_watch.add_argument("--series", type=str, help="Comma-separated Series Tickers", default="")
    parser_watch.add_argument("--tags", type=str, help="Comma-separated Tags", default="")
    parser_watch.add_argument("--category", type=str, help="Comma-separated Categories", default="")
    parser_watch.add_argument("--max-hours", type=float, help="Filter out markets closing after X hours", default=None)
    parser_watch.add_argument("--reset-int", type=float, help="Restart connection every X hours to clear memory/refresh markets", default=None)
    parser_watch.add_argument("--trade", action="store_true", help="Enable live trading")
    parser_watch.add_argument("--stake", type=int, help="How many contracts to wager", default=1)
    parser_watch.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.command == "search":
        asyncio.run(search_markets(args.series_ticker))
    elif args.command == "watch":
        series_tickers = [s.strip().upper() for s in args.series.split(",") if s.strip()] if args.series else []
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        categories = [c.strip() for c in args.category.split(",") if c.strip()] if args.category else []
        
        def get_max_close_ts():
            if args.max_hours is not None:
                return int(time.time()) + int(args.max_hours * 3600)
            return None
            
        async def fetch_markets_for_series(st: str) -> list[str]:
            url = f"https://api.elections.kalshi.com/trade-api/v2/markets"
            params = {"series_ticker": st, "status": "open", "limit": 1000}
            ts = get_max_close_ts()
            if ts:
                params["max_close_ts"] = ts
                print(f"Fetching open markets for series {st} with max_close_ts {ts}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
                    return [m.get("ticker") for m in (data.get("markets") or []) if m.get("ticker")]

        async def fetch_markets_for_tag(tag: str) -> list[str]:
            series_url = f"https://api.elections.kalshi.com/trade-api/v2/series"
            async with aiohttp.ClientSession() as session:
                async with session.get(series_url, params={"tags": tag}) as resp:
                    data = await resp.json()
                    st_list = [s.get("ticker") for s in (data.get("series") or []) if s.get("ticker")]
            
            markets = []
            for st in st_list:
                markets.extend(await fetch_markets_for_series(st))
            return markets
                    
        async def fetch_markets_for_category(category: str) -> list[str]:
            series_url = f"https://api.elections.kalshi.com/trade-api/v2/series"
            async with aiohttp.ClientSession() as session:
                async with session.get(series_url, params={"category": category}) as resp:
                    data = await resp.json()
                    st_list = [s.get("ticker") for s in (data.get("series") or []) if s.get("ticker")]
            
            markets = []
            for st in st_list:
                markets.extend(await fetch_markets_for_series(st))
            return markets

        async def fetch_all_markets() -> list[str]:
            url = f"https://api.elections.kalshi.com/trade-api/v2/markets"
            params = {"status": "open", "limit": 1000}
            ts = get_max_close_ts()
            if ts:
                params["max_close_ts"] = ts
            print(url,params)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
                    return [m.get("ticker") for m in (data.get("markets") or []) if m.get("ticker")]
            
        async def ping_latency() -> float:
            url = f"https://api.elections.kalshi.com/trade-api/v2/exchange/status"
            try:
                start_time = time.time()
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=5.0) as resp:
                        await resp.read()
                end_time = time.time()
                latency_ms = (end_time - start_time) * 1000
                print(f"Kalshi API Latency: {latency_ms:.2f}ms")
                return latency_ms
            except Exception as e:
                print(f"Failed to measure Kalshi API latency: {e}")
                return -1.0
                    
        async def watch_with_retries():
            empty_attempts = 0
            
            # Ping latency on startup
            await ping_latency()
            
            while empty_attempts < 5:
                all_tickers = []
                series_mapping = {}
                requested_groups = []
                print(f"series_tickers: {series_tickers}")
                print(f"tags: {tags}")
                print(f"categories: {categories}")
                for st in series_tickers:
                    req_id = f"series:{st}"
                    requested_groups.append(req_id)
                    if args.verbose:
                        print(f"Fetching open markets for series '{st}'...")
                    tickers = await fetch_markets_for_series(st)
                    all_tickers.extend(tickers)
                    for t in tickers:
                        series_mapping[t] = req_id
                
                for tg in tags:
                    req_id = f"tag:{tg}"
                    requested_groups.append(req_id)
                    if args.verbose:
                        print(f"Fetching open markets for tag '{tg}'...")
                    tickers = await fetch_markets_for_tag(tg)
                    all_tickers.extend(tickers)
                    for t in tickers:
                        series_mapping[t] = req_id
                
                for ctg in categories:
                    req_id = f"category:{ctg}"
                    requested_groups.append(req_id)
                    if args.verbose:
                        print(f"Fetching open markets for category '{ctg}'...")
                    tickers = await fetch_markets_for_category(ctg)
                    all_tickers.extend(tickers)
                    for t in tickers:
                        series_mapping[t] = req_id
                
                # Fetch all if no specific groups were requested
                if not requested_groups:
                    if args.verbose:
                        print(f"Fetching ALL open markets...")
                    tickers = await fetch_all_markets()
                    all_tickers.extend(tickers)
                    
                # De-duplicate tickers while preserving order
                all_tickers = list(dict.fromkeys(all_tickers))
                    
                if not all_tickers:
                    empty_attempts += 1
                    print(f"No open markets found. Attempt {empty_attempts}/5")
                    await asyncio.sleep(10)
                    continue
                    
                print(f"Starting monitor for {len(all_tickers)} markets across {len(series_tickers)} series, {len(tags)} tags, and {len(categories)} categories...")
                
                trade_enabled = args.trade
                stake = args.stake
                print(f"Trading Enabled: {trade_enabled} | Stake: {stake} contracts")
                
                monitor = KalshiArbMonitor(
                    all_tickers, 
                    trade=trade_enabled, 
                    stake=stake, 
                    verbose=args.verbose,
                    series_mapping=series_mapping,
                    requested_series=requested_groups,
                    reset_int_hours=args.reset_int
                )
                try:
                    await monitor.connect()
                    # If connect finishes normally, we shouldn't continue retrying endlessly
                    # connect() should fundamentally only return if it finishes (we don't want to loop endlessly when it succeeds and exits gracefully).
                    break
                except NoActiveBidsException:
                    if monitor.successful_period:
                        empty_attempts = 0
                    empty_attempts += 1
                    print(f"Connection reset requested due to no active bids. Attempt {empty_attempts}/5")
                    continue
                except KeyboardInterrupt:
                    print("\nShutting down monitor.")
                    break
                except Exception as e:
                    print(f"Monitor error: {e}")
                    await asyncio.sleep(5)
            
            if empty_attempts >= 5:
                print("No markets found 5 times in a row. Exiting.")
                
        asyncio.run(watch_with_retries())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down cleanly...")
