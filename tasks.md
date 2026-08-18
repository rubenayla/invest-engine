# Tasks

## Persist historical insider signal snapshots

- [ ] Store the insider-specific signal fields in the daily snapshot alongside the existing opportunity scores: insider score, buy and sell counts, net buy percentage, sell trend, buy trend, cluster score, and dollar conviction.
- [ ] Expose the stored insider snapshots through the dashboard API.
- [ ] Add a historical insider-signal view that shows how the signal and its underlying components change over time.
- [ ] Keep the existing transaction-history chart, and label its bars as gross buys and sells rather than net count.
