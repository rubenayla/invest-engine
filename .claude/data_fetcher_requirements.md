# Data Fetcher Requirements

## CRITICAL: Automatic Retry Logic

**Problem**: The user has reported 4+ times that failed stock fetches require manual re-runs.

**Requirement**: `scripts/data_fetcher.py` MUST have built-in retry logic:
- **6 retries maximum** per stock
- **Exponential backoff**: 5s, 10s, 20s, 40s, 80s, 160s between attempts
- **Only mark as failed** if all 6 retries are exhausted
- **No manual intervention** should be needed for rate-limited stocks

## Implementation Status

**✅ COMPLETE**: Retry logic fully implemented in `fetch_stock_data_sync()` with:
- Fixed indentation - all data fetching logic inside the `try` block
- `except` block catches failures and continues to next retry
- Only returns error dict if all 6 retries fail
- Logs each retry attempt with wait time

## Expected Behavior

```python
# User runs once:
uv run python scripts/data_fetcher.py --universe cached --force-refresh

# Script automatically:
# - Attempts each stock up to 6 times
# - Waits with exponential backoff between retries
# - Only fails stocks that genuinely can't be fetched after 6 attempts
# - NO manual re-running required
```

## User Frustration Level

**CRITICAL** - This has been requested 4+ times and keeps being forgotten. This MUST be fixed properly.
