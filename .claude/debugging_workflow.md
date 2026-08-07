# Dashboard Debugging Workflow

Systematic approach to debug dashboard issues, working backwards from user-visible problems to root causes.

## Level 1: Dashboard Display
**Check:** http://localhost:8080
- Verify all columns appear (DCF, RIM, Simple Ratios, NN, etc.)
- Check if values show "--" or actual numbers
- Verify values are NOT all identical

**If issues found → Go to Level 2**

## Level 2: Dashboard Data File
**Check:** `dashboard/dashboard_data.json`
- Verify structure is valid JSON
- Check stock count (expect ~289 stocks)
- Look for identical prediction values (bug indicator)
- Verify fair_value, current_price, suitable fields present

**If data missing/identical → Go to Level 3**

## Level 3: Valuation Scripts
**Check:** Did valuation generation run successfully?

### 3A: Classic Valuations
- Check logs: `logs/classic_valuations_final.log`
- Expect: DCF ~255 success, RIM ~208 success, Simple Ratios ~258 success

**If failed → Go to Level 4A (Stock Cache)**

### 3B: Neural Network Predictions
- Check if .pth model files exist: `find . -name "*.pth"`
- Check prediction logs

**If no models → Go to Level 5 (Training)**
**If predictions failed → Go to Level 4B (NN Cache)**

## Level 4A: Stock Data Cache
**Check:** `data/stock_cache/` (expect 435 files)
- Verify cache files exist
- Sample key stocks (AAPL, MSFT, GOOGL, TSLA) for data quality
- Check for currentPrice, trailingEps, etc.

**If empty/corrupted → Re-fetch with slow rate to avoid rate limiting**

## Level 4B: Neural Network Training Cache
**Check:** Historical price data cache for NN training
- Look for cache files (location varies by implementation)
- Check cache generation logs

**If missing → Regenerate cache**

## Level 5: Neural Network Training
**Check:** Are trained model files (.pth) present?
- Search: `find . -name "*.pth" -o -name "*.pt"`
- Expected locations: models/neural_network/models/, models/, checkpoints/

**If no models → Train the model**

## Level 6: System Compatibility
**Check:** Dependencies and environment
- Python/uv environment
- PyTorch, yfinance versions
- Database schema (data/valuations.db)

## Key Learnings
1. All identical predictions = model file doesn't exist
2. Dashboard shows "--" = data exists but invalid (all identical or unsuitable)
3. Empty cache after fetch = rate limiting (wait 5-10 min before retry)
4. Classic models work, NN doesn't = missing .pth files
5. Always check backwards from what user sees
