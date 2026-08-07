# Technical Analysis Notes

This project includes a lightweight, data-driven way to pick limit-order levels
using the local price history cache. It is **not** predictive; it just anchors
entries around recent support levels and moving averages.

## Data Source

The data comes from `data/stock_data.db`, table `price_history`, which is filled
by `scripts/data_fetcher.py`. If the cache is old, update it first.

Recommended refresh:

```bash
uv run python scripts/update_all.py --universe all
```

## Method Used

For a given ticker:

1. **Latest close** from the most recent row.
2. **52-week high/low** from the last ~252 trading days.
3. **90-day low** to capture recent pullback extremes.
4. **Moving averages**: 20/50/200-day simple averages.
5. **Support buckets** from recent lows:
   - Take last ~180 days of daily lows.
   - Bucket to the nearest $0.25.
   - The most frequent buckets are treated as support zones.
6. **Volume check**: 10-day average volume for context.

Entry logic (example):

- **High-probability fill**: near the strongest support bucket or MA cluster.
- **Lower-probability, better price**: near the next support bucket or 90-day low.

## Example Script (PTON)

```python
import sqlite3
from statistics import mean

conn = sqlite3.connect('data/stock_data.db')
conn.row_factory = sqlite3.Row

ticker = 'PTON'
rows = conn.execute(
    '''
    SELECT date, open, high, low, close, volume
    FROM price_history
    WHERE ticker = ?
    ORDER BY date
    ''',
    (ticker,)
).fetchall()

prices = [row['close'] for row in rows if row['close'] is not None]
volumes = [row['volume'] for row in rows if row['volume'] is not None]

latest = rows[-1]
latest_close = latest['close']

window_52w = prices[-252:] if len(prices) >= 252 else prices
low_52w = min(window_52w)
high_52w = max(window_52w)

def ma(series, n):
    if len(series) < n:
        return None
    return mean(series[-n:])

ma20 = ma(prices, 20)
ma50 = ma(prices, 50)
ma200 = ma(prices, 200)

window_90 = rows[-90:] if len(rows) >= 90 else rows
low_90 = min(r['low'] for r in window_90 if r['low'] is not None)

avg_vol_10 = mean(volumes[-10:]) if len(volumes) >= 10 else mean(volumes)

window_180 = rows[-180:] if len(rows) >= 180 else rows
buckets = {}
for r in window_180:
    low = r['low']
    if low is None:
        continue
    bucket = round(low / 0.25) * 0.25
    buckets[bucket] = buckets.get(bucket, 0) + 1

support = sorted(buckets.items(), key=lambda x: x[1], reverse=True)[:3]

print(f'Latest close: {latest_close:.2f}')
print(f'52w low/high: {low_52w:.2f} / {high_52w:.2f}')
print(f'90d low: {low_90:.2f}')
print(f'MA20/50/200: {ma20:.2f} / {ma50:.2f} / {ma200:.2f}')
print(f'Avg volume (10d): {avg_vol_10:,.0f}')
print('Support buckets:')
for level, count in support:
    print(f'  {level:.2f} ({count} hits)')

conn.close()
```

## Notes

- This is a **support-focused** method, not momentum.
- It relies on cached prices; refresh data if it is stale.
- For higher-priced stocks, you may want a larger bucket size than `$0.25`.
