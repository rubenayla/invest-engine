import asyncio
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.data_fetcher import AsyncStockDataFetcher

async def update_tickers(tickers: list[str]):
    async with AsyncStockDataFetcher(max_workers=5) as fetcher:
        results = await fetcher.fetch_multiple_stocks(tickers, max_concurrent=5)
    
    for ticker, data in results.items():
        if 'error' in data:
            print(f"Error updating {ticker}: {data['error']}")
        else:
            print(f"Successfully updated {ticker}")

if __name__ == "__main__":
    tickers = ['BE', 'MOH', 'SONY', 'SYF']
    if len(sys.argv) > 1:
        tickers = sys.argv[1:]
    
    asyncio.run(update_tickers(tickers))
