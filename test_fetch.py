import aiohttp
import asyncio

async def test():
    tag = "15m"
    tag_url = f"https://gamma-api.polymarket.com/tags/slug/{tag}"
    print(f"Fetching tag from: {tag_url}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(tag_url) as resp:
            tag_data = await resp.json()
            print("Tag Data:", tag_data)
            
            tag_id = tag_data.get("id")
            if not tag_id:
                print("No tag_id found. Exiting.")
                return
                
            url = f"https://gamma-api.polymarket.com/markets"
            params = {"tag_id": tag_id, "active": "true", "closed": "false", "limit": 100}
            print(f"\nFetching markets from: {url} with params: {params}")
            
            async with session.get(url, params=params) as resp2:
                markets_data = await resp2.json()
                print(f"Returned {len(markets_data)} raw markets.")
                if markets_data:
                    m = markets_data[0]
                    print(f"First market sample: {m.get('question', '')}")
                    print(f"Condition ID: {m.get('conditionId', '')}")
                    print(f"clobTokenIds: {m.get('clobTokenIds', [])}")

if __name__ == "__main__":
    asyncio.run(test())
