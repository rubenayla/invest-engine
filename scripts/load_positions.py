"""
Load current portfolio positions from the local private vault.

Public-repo safe: reads from `~/vault/finance/main.beancount` if present
(the vault is a separate, private repo on this machine). On any other
machine — CI, Hetzner, a fresh clone — the path resolves to nothing
and `get_positions()` returns an empty dict, so callers fall back to
"no positions known" instead of crashing.

Requires `beancount` in the active env. Add with:
    uv add beancount

Usage:
    from scripts.load_positions import get_positions
    positions = get_positions()
    # {"MOH": {"shares": 48.54, "currency": "USD", "accounts": [...]}, ...}
"""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

VAULT_BEANCOUNT = Path.home() / "vault" / "finance" / "main.beancount"


def get_positions() -> dict[str, dict]:
    """Return aggregated stock/crypto positions across all brokerage accounts.

    Returns {} when the vault file is unreachable or beancount isn't installed —
    callers should treat empty as "unknown positions," not "zero positions."
    """
    if not VAULT_BEANCOUNT.exists():
        return {}

    try:
        from beancount import loader
        from beancount.core import inventory
        from beancount.core.data import Open
    except ImportError:
        return {}

    entries, errors, _options = loader.load_file(str(VAULT_BEANCOUNT))
    if errors:
        # Don't crash analyses on parse errors — just skip the personal data.
        return {}

    # Walk the entries and accumulate position units by commodity, restricted
    # to brokerage / crypto accounts.
    holdings: dict[str, dict] = defaultdict(
        lambda: {"shares": 0.0, "currency": None, "accounts": set()}
    )
    relevant_prefixes = ("Assets:Brokerage", "Assets:Crypto")

    for entry in entries:
        if not hasattr(entry, "postings"):
            continue
        for posting in entry.postings:
            if not posting.account.startswith(relevant_prefixes):
                continue
            units = posting.units
            if units is None:
                continue
            currency = units.currency
            # Skip cash legs (EUR/USD/JPY); we only want tickers / crypto.
            if currency in {"EUR", "USD", "JPY", "GBP", "CHF"}:
                continue
            holdings[currency]["shares"] += float(units.number)
            holdings[currency]["accounts"].add(posting.account)
            if posting.cost is not None:
                holdings[currency]["cost_currency"] = posting.cost.currency

    # Drop tickers that net to zero (sold out).
    return {
        ticker: {
            "shares": round(data["shares"], 6),
            "accounts": sorted(data["accounts"]),
            "cost_currency": data.get("cost_currency"),
        }
        for ticker, data in holdings.items()
        if abs(data["shares"]) > 1e-9
    }


if __name__ == "__main__":
    import json

    positions = get_positions()
    if not positions:
        print(f"No positions found (vault file: {VAULT_BEANCOUNT})")
        print("If running on this machine and the file exists, install beancount:")
        print("    uv add beancount")
    else:
        print(json.dumps(positions, indent=2, default=list))
