# Completed tasks

## 2026-08-18 — Persist historical insider signal snapshots

- [x] Store the insider-specific signal fields in the daily snapshot alongside the existing opportunity scores: insider score, buy and sell counts, net buy percentage, sell trend, buy trend, cluster score, and dollar conviction.
- [x] Expose the stored insider snapshots through the dashboard API.
- [x] Add a historical insider-signal view that shows how the signal and its underlying components change over time.
- [x] Keep the existing transaction-history chart, and label its bars as gross buys and sells rather than net count.

Completed by adding scanner-schema migrations and upserts, a backward-compatible `snapshots` API response, and a dashboard history view with gross transaction labels.
