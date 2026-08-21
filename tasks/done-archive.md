# Completed tasks

## 2026-08-18 — Persist historical insider signal snapshots

- [x] Store the insider-specific signal fields in the daily snapshot alongside the existing opportunity scores: insider score, buy and sell counts, net buy percentage, sell trend, buy trend, cluster score, and dollar conviction.
- [x] Expose the stored insider snapshots through the dashboard API.
- [x] Add a historical insider-signal view that shows how the signal and its underlying components change over time.
- [x] Keep the existing transaction-history chart, and label its bars as gross buys and sells rather than net count.

Completed by adding scanner-schema migrations and upserts, a backward-compatible `snapshots` API response, and a dashboard history view with gross transaction labels.

## 2026-08-21 — Deploy investment dashboard code to y540

- [x] Add a GitHub Actions deployment job for `main` that updates `/home/rubenayla/repos/invest-engine` on y540 and restarts the user dashboard server after checks pass.

Completed and verified by GitHub Actions run `32470336800`: the test job passed, the deployment connected through Cloudflare Access SSH, regenerated the dashboard, restarted `invest-dashboard.service`, and passed the dashboard health check at commit `1acfac8fb162e4f029ee10b45a73ce38388f4680`.
