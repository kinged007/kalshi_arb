import argparse
import asyncio
import aiohttp
import time
import sys
from dotenv import load_dotenv

from poly_ws import PolyArbMonitor, NoActiveBidsException

sys.stdout.reconfigure(line_buffering=True)
load_dotenv()

async def search_markets(slug_or_id: str):
    """Fetch event details and associated markets for a given slug or ID."""
    
    url = f"https://gamma-api.polymarket.com/events"
    params = {"slug": slug_or_id}
    
    async with aiohttp.ClientSession() as session:
        print(f"Fetching event data for '{slug_or_id}'...")
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            
            if not data:
                print(f"No events found for slug: {slug_or_id}\n")
                return
                
            event = data[0] if isinstance(data, list) else data
            
            print("=" * 60)
            print(f"Event Title: {event.get('title')}")
            print(f"Start Date: {event.get('startDate')} | End Date: {event.get('endDate')}")
            print("=" * 60)
            
            markets = event.get('markets', [])
            if not markets:
                print("No open markets found for this event.\n")
                return
                
            print(f"\nFound {len(markets)} active markets across event {slug_or_id}:\n")
            
            for m in markets:
                cond_id = m.get('conditionId', 'Unknown')
                question = m.get('question', 'Unknown Question')
                
                print(f"  [{cond_id[:8]}...] {question}")
            print()

def main():
    parser = argparse.ArgumentParser(description="Polymarket Arbitrage Monitor Phase 1")
    subparsers = parser.add_subparsers(dest="command", help="Command to run", required=True)
    
    # Subparser for search
    parser_search = subparsers.add_parser("search", help="Search for active events")
    parser_search.add_argument("slug", type=str, help="Event Slug (e.g., 'will-bitcoin-hit-100k-in-2024')")
    
    # Subparser for watch
    parser_watch = subparsers.add_parser("watch", help="Watch specific events or tags for arbitrage")
    parser_watch.add_argument("--slugs", type=str, help="Comma-separated Event Slugs", default="")
    parser_watch.add_argument("--tags", type=str, help="Comma-separated Tags (e.g. 'sports', 'politics')", default="")
    parser_watch.add_argument("--reset-int", type=float, help="Restart connection every X hours clear memory/refresh markets", default=None)
    parser_watch.add_argument("--trade", action="store_true", help="Enable live trading (STUBBED Phase 1)")
    parser_watch.add_argument("--stake", type=int, help="How many contracts to wager (min 5 on Polymarkets)", default=5)
    parser_watch.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.command == "search":
        asyncio.run(search_markets(args.slug))
    elif args.command == "watch":
        slugs = [s.strip() for s in args.slugs.split(",") if s.strip()] if args.slugs else []
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []

        async def fetch_markets_for_slug(slug: str) -> list[dict]:
            url = f"https://gamma-api.polymarket.com/events"
            params = {"slug": slug, "active": "true", "closed": "false"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
                    markets = []
                    events = data if isinstance(data, list) else [data]
                    for event in events:
                        for m in event.get("markets", []):
                            tokens = m.get("clobTokenIds", [])
                            # Generally tokens are [YesToken, NoToken] if standard binary
                            if len(tokens) >= 2:
                                markets.append({
                                    'condition_id': m.get('conditionId', ''),
                                    'question': m.get('question', ''),
                                    'yes_token': str(tokens[0]),
                                    'no_token': str(tokens[1])
                                })
                    return markets

        async def fetch_markets_for_tag(tag: str) -> list[dict]:
            # Step 1: Get the tag ID
            tag_slug = tag.lower()
            tag_url = f"https://gamma-api.polymarket.com/tags/slug/{tag_slug}"
            async with aiohttp.ClientSession() as session:
                async with session.get(tag_url) as resp:
                    if resp.status != 200:
                        if args.verbose:
                            print(f"Failed to find tag slug '{tag_slug}'. HTTP {resp.status}")
                        return []
                    tag_data = await resp.json()
                    tag_id = tag_data.get("id")
                    if not tag_id:
                        return []
            
            # Step 2: Fetch markets for that tag ID
            url = f"https://gamma-api.polymarket.com/markets"
            params = {"tag_id": tag_id, "active": "true", "closed": "false", "limit": 100}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
                    markets = []
                    # Data could be list of markets directly from /markets
                    markets_data = data if isinstance(data, list) else []
                    
                    if args.verbose:
                        print(f"API Returned {len(markets_data)} raw markets for tag {tag} ({tag_id})")
                        
                    for m in markets_data:
                        raw_tokens = m.get("clobTokenIds", "[]")
                        if isinstance(raw_tokens, str):
                            import json
                            try:
                                tokens = json.loads(raw_tokens)
                            except:
                                tokens = []
                        else:
                            tokens = raw_tokens
                            
                        condition_id = m.get('conditionId', '')
                        if args.verbose and not tokens:
                             print(f"No clobTokenIds for market {m.get('question', '')} - cond: {condition_id}")
                             
                        if len(tokens) >= 2:
                            markets.append({
                                'condition_id': condition_id,
                                'question': m.get('question', ''),
                                'yes_token': str(tokens[0]),
                                'no_token': str(tokens[1])
                            })
                    return markets

        async def fetch_all_markets() -> list[dict]:
            url = f"https://gamma-api.polymarket.com/events"
            params = {"active": "true", "closed": "false", "limit": 300}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
                    markets = []
                    events = data if isinstance(data, list) else []
                    for event in events:
                        for m in event.get("markets", []):
                            tokens = m.get("clobTokenIds", [])
                            if len(tokens) >= 2:
                                markets.append({
                                    'condition_id': m.get('conditionId', ''),
                                    'question': m.get('question', ''),
                                    'yes_token': str(tokens[0]),
                                    'no_token': str(tokens[1])
                                })
                    return markets

        async def ping_latency() -> float:
            url = f"https://gamma-api.polymarket.com/events?limit=1"
            try:
                start_time = time.time()
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=5.0) as resp:
                        await resp.read()
                end_time = time.time()
                latency_ms = (end_time - start_time) * 1000
                print(f"Polymarket Gamma API Latency: {latency_ms:.2f}ms")
                return latency_ms
            except Exception as e:
                print(f"Failed to measure Polymarket API latency: {e}")
                return -1.0

        async def watch_with_retries():
            empty_attempts = 0
            
            # Ping latency on startup
            await ping_latency()
            
            while empty_attempts < 5:
                all_markets = []
                # Keep track of condition IDs to deduplicate
                seen_conditions = set()

                for slug in slugs:
                    if args.verbose:
                        print(f"Fetching open markets for slug '{slug}'...")
                    markets = await fetch_markets_for_slug(slug)
                    for m in markets:
                        if m['condition_id'] not in seen_conditions:
                            seen_conditions.add(m['condition_id'])
                            all_markets.append(m)
                
                for tag in tags:
                    if args.verbose:
                        print(f"Fetching open markets for tag '{tag}'...")
                    markets = await fetch_markets_for_tag(tag)
                    for m in markets:
                        if m['condition_id'] not in seen_conditions:
                            seen_conditions.add(m['condition_id'])
                            all_markets.append(m)
                
                # Fetch all if no specific groups were requested
                if not slugs and not tags:
                    if args.verbose:
                        print(f"Fetching ALL open markets (limit 300 events)...")
                    markets = await fetch_all_markets()
                    for m in markets:
                        if m['condition_id'] not in seen_conditions:
                            seen_conditions.add(m['condition_id'])
                            all_markets.append(m)
                    
                if not all_markets:
                    empty_attempts += 1
                    print(f"No open markets found. Attempt {empty_attempts}/5")
                    await asyncio.sleep(10)
                    continue
                    
                print(f"Starting monitor for {len(all_markets)} markets across {len(slugs)} slugs and {len(tags)} tags...")
                
                trade_enabled = args.trade
                stake = args.stake
                # if trade_enabled and stake < 5:
                #     print("⚠️  Polymarket minimum order size is 5 contracts. Adjusting stake to 5.")
                #     stake = 5
                print(f"Trading Enabled: {trade_enabled} | Stake: {stake} contracts")
                
                monitor = PolyArbMonitor(
                    all_markets, 
                    trade=trade_enabled, 
                    stake=stake, 
                    verbose=args.verbose,
                    reset_int_hours=args.reset_int
                )
                try:
                    await monitor.connect()
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
