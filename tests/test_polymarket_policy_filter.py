"""Unit tests for Polymarket Trump-policy market keyword filter."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

from polymarket_lookup import classify_trump_policy_market


# Each row: (question, description, expected_category_or_None)
# expected = None means the market should be filtered OUT.
KEYWORD_CASES = [
    # ---- Tariffs ----
    ('Will Trump impose tariffs on EU before June 30?', '', 'tariffs'),
    ('Trump 50% tariffs on Mexico in 2026?', '', 'tariffs'),
    ('Will the US announce a trade deal with India by July?', '', 'tariffs'),
    ('Will tariffs on imported steel rise to 25%?', '', 'tariffs'),

    # ---- Fed actions ----
    ('Will the Fed cut rates in May 2026?', '', 'fed_actions'),
    ('Will Trump try to fire Powell as Fed Chair before he leaves?', '',
     'fed_actions'),
    ('FOMC rate decision: hold or cut?', '', 'fed_actions'),

    # ---- Executive orders ----
    ('Will Trump sign an executive order on crypto by May 31?', '',
     'executive_orders'),

    # ---- Cabinet appointments ----
    ('Will Trump nominate Todd Blanche as Attorney General?', '',
     'cabinet_appointments'),
    ('Will the Senate confirm the nominee by June?', 'Trump nominee', 'cabinet_appointments'),

    # ---- Legislation ----
    ('Will Congress pass the tax bill by year end?', 'Trump-backed bill',
     'legislation'),
    ('Will the debt ceiling be raised by July?', 'Trump signs', 'legislation'),

    # ---- China ----
    ('Will Trump meet Xi Jinping by June 30?', '', 'china'),

    # ---- Energy / oil ----
    ('Will Trump open ANWR for oil drilling in 2026?', '', 'energy_oil'),

    # ---- Crypto ----
    ('Will Trump establish a strategic Bitcoin reserve?', '', 'crypto'),

    # ---- Immigration ----
    ('Will Trump deport 1M migrants by Q4 2026?', '', 'immigration'),

    # ---- Foreign policy ----
    ('Will Trump agree to Iranian enrichment of uranium by May 31?', '',
     'foreign_policy'),
    ('Will the Russia-Ukraine ceasefire hold under Trump?', '', 'foreign_policy'),

    # ---- Should be filtered out (noise) ----
    ('Will Trump’s approval rating be between 39.0 and 39.4 on May 1?', '',
     None),
    ('Will Trump say "Unaffordable Care Act" at The Villages on May 1?', '',
     None),
    ('Will Donald Trump visit Pennsylvania in 2026?', '', None),
    ('Will Trump sell 1k-2.5k Gold Cards in 2026?', '', None),
    ('Will Trump say "RINO" or "Republican in Name Only" in April?', '', None),
    ('Will Donald Trump announce a presidential run before 2027?', '', None),

    # ---- Should be filtered out (no Trump relevance + non-policy) ----
    ('Exact Score: Aston Villa 0-3 Nottingham?', '', None),
    ('Will Bitcoin hit $200k in 2026?', '', None),
    ('Will the Lakers win game 7?', '', None),

    # ---- Edge: empty / malformed ----
    ('', '', None),
]


@pytest.mark.parametrize('question,description,expected', KEYWORD_CASES)
def test_classify_trump_policy_market(question, description, expected):
    """Each known question maps to the right category (or filters out)."""
    result = classify_trump_policy_market(question, description)
    assert result == expected, (
        f'Question {question!r} -> got {result!r}, expected {expected!r}'
    )


def test_classifier_returns_none_for_low_signal_noise_even_with_trump():
    """An approval-rating market with the word 'tariff' in description is
    still noise — the filter looks at question first."""
    result = classify_trump_policy_market(
        'Trump approval rating on May 1?',
        'Tariff policy may affect approval...',
    )
    assert result is None


def test_classifier_handles_tariff_without_trump_token():
    """Tariff markets are de-facto Trump-policy under his administration even
    if his name isn't in the question."""
    result = classify_trump_policy_market(
        'Will the US impose 25% tariffs on EU steel by July?',
        '',
    )
    assert result == 'tariffs'
