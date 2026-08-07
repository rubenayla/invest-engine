"""
Unit tests for Truth Social NER extraction (regex + dictionary).

Covers cashtag matching, alias dictionary lookup, sector keywords, and
country / nationality forms. Hand-crafted sample posts mirror the kinds
of statements Trump posts that we want to surface as tradable signals.
"""

from __future__ import annotations

import pytest

from invest.data.truth_social_fetcher import (
    extract_countries,
    extract_sectors,
    extract_tickers,
    parse_status,
    strip_html,
)


class TestStripHtml:
    def test_strips_paragraph_tags(self) -> None:
        html = '<p>Hello world.</p><p>Second line.</p>'
        assert strip_html(html) == 'Hello world. Second line.'

    def test_handles_breaks(self) -> None:
        html = '<p>Line one<br>Line two<br/>Line three</p>'
        out = strip_html(html)
        assert 'Line one' in out and 'Line two' in out and 'Line three' in out

    def test_empty_input(self) -> None:
        assert strip_html('') == ''
        assert strip_html(None) == ''


class TestExtractTickers:
    def test_cashtag_basic(self) -> None:
        text = 'Buying $AAPL today, also looking at $TSLA.'
        assert extract_tickers(text) == ['AAPL', 'TSLA']

    def test_cashtag_with_exchange_suffix(self) -> None:
        text = 'Japan trade with $7203.T looking strong'
        assert '7203.T' in extract_tickers(text)

    def test_blocklist_filters_acronyms(self) -> None:
        text = 'The $USA is great, $USD strong, $CEO of $AAPL'
        out = extract_tickers(text)
        assert 'AAPL' in out
        assert 'USA' not in out
        assert 'USD' not in out
        assert 'CEO' not in out

    def test_alias_dict_matches_company_name(self) -> None:
        text = 'I love Apple products and Tesla cars.'
        out = extract_tickers(text)
        assert 'AAPL' in out
        assert 'TSLA' in out

    def test_longer_alias_wins_over_shorter(self) -> None:
        # "u.s. steel" must produce X, not USA->???
        text = 'U.S. Steel is being treated unfairly by foreign dumpers.'
        out = extract_tickers(text)
        assert 'X' in out

    def test_word_boundary_prevents_false_positive(self) -> None:
        # "intelligence" must not trigger Intel
        text = 'Intelligence agencies overstep their authority.'
        assert 'INTC' not in extract_tickers(text)

    def test_dedupe(self) -> None:
        text = '$AAPL $AAPL Apple Apple'
        out = extract_tickers(text)
        assert out.count('AAPL') == 1

    def test_extra_alias_dict_overlay(self) -> None:
        extra = {'foobar inc': 'FOO'}
        text = 'Foobar Inc is great'
        # Note: alias matching is on the cleaned/lowered name; we provide
        # the lowercased key directly
        out = extract_tickers(text, alias_dict=extra)
        assert 'FOO' in out

    def test_empty_input(self) -> None:
        assert extract_tickers('') == []
        assert extract_tickers(None) == []


class TestExtractSectors:
    def test_semiconductors(self) -> None:
        text = 'The semiconductor industry must come back to America!'
        assert 'semiconductors' in extract_sectors(text)

    def test_oil_keywords(self) -> None:
        text = 'OPEC must lower oil prices, gasoline is too expensive.'
        out = extract_sectors(text)
        assert 'oil' in out

    def test_defense(self) -> None:
        text = 'Our military is the strongest in the world.'
        assert 'defense' in extract_sectors(text)

    def test_steel(self) -> None:
        text = 'Tariffs on Steel and Aluminum will protect US workers.'
        assert 'steel' in extract_sectors(text)

    def test_ai_with_word_boundary(self) -> None:
        # bare " AI " should hit; "said" must not
        text = 'AI is the future of America.'
        assert 'AI' in extract_sectors(text)
        # negative case
        assert 'AI' not in extract_sectors('She said hello.')

    def test_empty(self) -> None:
        assert extract_sectors('') == []
        assert extract_sectors('Just a normal day.') == []


class TestExtractCountries:
    def test_china(self) -> None:
        text = 'China is taking advantage of us!'
        assert 'China' in extract_countries(text)

    def test_chinese_adjective(self) -> None:
        text = 'Chinese tariffs will be increased to 60%.'
        assert 'China' in extract_countries(text)

    def test_mexico(self) -> None:
        text = 'Mexico must stop the flow of fentanyl.'
        assert 'Mexico' in extract_countries(text)

    def test_longest_match_south_korea(self) -> None:
        text = 'South Korea must pay more for our protection.'
        assert 'South Korea' in extract_countries(text)

    def test_multiple_countries(self) -> None:
        text = 'China, Mexico, and Canada all face new tariffs.'
        out = extract_countries(text)
        assert set(out) >= {'China', 'Mexico', 'Canada'}

    def test_eu(self) -> None:
        text = 'The European Union is being unfair.'
        assert 'European Union' in extract_countries(text)

    def test_dedupe(self) -> None:
        text = 'China, Chinese, China again.'
        out = extract_countries(text)
        assert out.count('China') == 1

    def test_empty(self) -> None:
        assert extract_countries('') == []


class TestParseStatus:
    def test_full_round_trip(self) -> None:
        status = {
            'id': '12345',
            'created_at': '2026-04-30T12:00:00.000Z',
            'content': '<p>Tariffs on Chinese semiconductors will save $INTC and Apple jobs!</p>',
        }
        row = parse_status(status)
        assert row is not None
        assert row['post_id'] == '12345'
        assert 'INTC' in row['extracted_tickers']
        assert 'AAPL' in row['extracted_tickers']
        assert 'semiconductors' in row['extracted_sectors']
        assert 'China' in row['extracted_countries']
        assert row['posted_at'].startswith('2026-04-30T12:00:00')

    def test_image_only_post_skipped(self) -> None:
        status = {
            'id': '12345',
            'created_at': '2026-04-30T12:00:00.000Z',
            'content': '',
        }
        assert parse_status(status) is None

    def test_missing_fields_returns_none(self) -> None:
        assert parse_status({}) is None
        assert parse_status({'id': '1'}) is None
        assert parse_status({'created_at': '2026-04-30T12:00:00Z'}) is None


class TestRealisticPosts:
    """Spot-check the NER on Trump-style sample posts."""

    @pytest.mark.parametrize('text,expect_tickers,expect_sectors,expect_countries', [
        # Tariff post
        (
            'Effective immediately, 60% tariffs on all Chinese imports. '
            'Made in America! Bring back our steel and aluminum jobs.',
            [],  # no specific ticker
            ['steel'],
            ['China'],
        ),
        # Direct company shoutout
        (
            'Tim Apple is doing a fantastic job. Bringing manufacturing back to '
            'the USA. $AAPL is a great American company!',
            ['AAPL'],
            [],
            [],
        ),
        # Multi-entity
        (
            'TSMC must build their chips in America. Taiwan is losing to '
            'China. Intel and $NVDA need our support — semiconductor leadership '
            'is national security.',
            ['TSM', 'NVDA', 'INTC'],
            ['semiconductors'],
            ['Taiwan', 'China'],
        ),
    ])
    def test_realistic_extraction(
        self,
        text: str,
        expect_tickers: list,
        expect_sectors: list,
        expect_countries: list,
    ) -> None:
        out_tickers = set(extract_tickers(text))
        out_sectors = set(extract_sectors(text))
        out_countries = set(extract_countries(text))
        assert set(expect_tickers).issubset(out_tickers), \
            f'Missing tickers: {set(expect_tickers) - out_tickers}'
        assert set(expect_sectors).issubset(out_sectors), \
            f'Missing sectors: {set(expect_sectors) - out_sectors}'
        assert set(expect_countries).issubset(out_countries), \
            f'Missing countries: {set(expect_countries) - out_countries}'
