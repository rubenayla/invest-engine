#!/usr/bin/env python3
"""
Run daily opportunity scanner.

Purpose:
- Run a *daily* scan over the stock universe.
- Notify *only* when an opportunity clears a dynamically adjusted threshold that
  targets ~1 notification per week on average over the long run (not "every
  week" on a schedule).

Delivery model:
- This script prints the notification message to stdout.
- A scheduler (systemd timer / OpenClaw / cron) should capture stdout and
  forward it to Telegram (or any channel).

Usage:
    uv run python scripts/run_opportunity_scan.py
    uv run python scripts/run_opportunity_scan.py --dry-run
    uv run python scripts/run_opportunity_scan.py --preview
    uv run python scripts/run_opportunity_scan.py --status
    uv run python scripts/run_opportunity_scan.py --weekly-report
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'src'))

from invest.config.logging_config import setup_logging
from invest.scanner import OpportunityScanner


def print_score_summary(score):
    """Print a compact score summary."""
    print(f"  {score.ticker:6} {score.opportunity_score:5.1f}  "
          f"Q:{score.quality_score:4.0f} V:{score.value_score:4.0f} "
          f"G:{score.growth_score:4.0f} R:{score.risk_score:4.0f} "
          f"C:{score.catalyst_score:4.0f}  "
          f"${score.current_price:.2f}")


def main() -> int:
    setup_logging(log_file_path="logs/opportunity_scan.log")

    parser = argparse.ArgumentParser(
        description='Run daily opportunity scanner'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without recording to database or sending notifications'
    )
    parser.add_argument(
        '--preview',
        action='store_true',
        help='Preview top 10 opportunities without recording'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Show current scanner status'
    )
    parser.add_argument(
        '--weekly-report',
        action='store_true',
        help='Generate weekly summary report'
    )
    parser.add_argument(
        '--tickers',
        type=str,
        help='Comma-separated list of tickers to scan (default: all)'
    )
    parser.add_argument(
        '--source',
        type=str,
        choices=['all', 'politician-pass-buys', 'politician-pass-sells'],
        default='all',
        help=(
            'Universe source. "all" (default) scans every ticker in the database. '
            '"politician-pass-buys" restricts to tickers with a recent buy from a '
            'gate-PASS politician (Pelosi today). "politician-pass-sells" does the '
            'symmetric thing for backtested sell signals (Tuberville).'
        ),
    )
    parser.add_argument(
        '--lookback-days',
        type=int,
        default=180,
        help='How many days back to look when --source is politician-pass-* (default: 180)',
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Only output notification messages (for OpenClaw)'
    )
    args = parser.parse_args()

    scanner = OpportunityScanner()

    # Parse tickers if provided
    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]
    elif args.source != 'all':
        direction = 'P' if args.source == 'politician-pass-buys' else 'S'
        tickers = scanner.reader.get_tickers_with_gate_pass_politician_trade(
            lookback_days=args.lookback_days, direction=direction,
        )
        if not tickers:
            print(
                f'No tickers found for source={args.source} '
                f'(lookback {args.lookback_days}d). Nothing to scan.'
            )
            return 0
        if not args.quiet:
            print(
                f'Universe restricted to {len(tickers)} ticker(s) with a '
                f'gate-PASS politician {"buy" if direction == "P" else "sell"} '
                f'in the last {args.lookback_days} days: {", ".join(tickers)}'
            )

    # Status mode
    if args.status:
        status = scanner.get_status()
        print("\n📊 Scanner Status")
        print("=" * 40)
        print(f"Current threshold:    {status['current_threshold']:.1f}")
        print(f"Notification rate:    {status['notification_rate_per_week']:.2f}/week")
        print(f"Days since last:      {status['days_since_last_notification']}")
        print(f"Target rate:          {status['target_rate']}/week")
        print(f"Threshold range:      {status['min_threshold']} - {status['max_threshold']}")
        print("\nRecent history:")
        for h in status['recent_history'][:7]:
            notif = "✅" if h['notification_sent'] else "  "
            ticker = h['notified_ticker'] or ""
            print(f"  {h['date']} | T:{h['threshold']:5.1f} | Best:{h['best_score'] or 0:5.1f} | {notif} {ticker}")
        return 0

    # Weekly report mode
    if args.weekly_report:
        report = scanner.generate_weekly_report()
        print(report)
        return 0

    # Preview mode
    if args.preview:
        if not args.quiet:
            print("\n🔍 Previewing Top Opportunities")
            print("=" * 60)

        top = scanner.preview_top_opportunities(tickers=tickers, limit=10)
        threshold = scanner.threshold_manager.calculate_adjusted_threshold()

        if not args.quiet:
            print(f"Current threshold: {threshold:.1f}\n")
            print("Ticker  Score   Q    V    G    R    C     Price")
            print("-" * 60)

        for score in top:
            if args.quiet:
                if score.opportunity_score >= threshold:
                    notif = scanner.notifier.format_notification(
                        score, threshold,
                        is_exceptional=score.opportunity_score >= 90
                    )
                    print(notif)
                    break
            else:
                marker = "⭐" if score.opportunity_score >= threshold else "  "
                print(f"{marker}", end="")
                print_score_summary(score)

        return 0

    # Full scan mode
    if not args.quiet:
        print("\n🚀 Running Opportunity Scanner")
        print("=" * 60)

    result = scanner.scan(tickers=tickers, dry_run=args.dry_run)

    if not args.quiet:
        print(f"\nScan completed for {result.date}")
        print(f"  Stocks scanned: {result.stocks_scanned}")
        print(f"  Threshold used: {result.threshold_used:.1f}")
        print(f"  Above threshold: {result.stocks_above_threshold}")

        if result.best_opportunity:
            print(f"\n📈 Best opportunity: {result.best_opportunity.ticker} "
                  f"(score: {result.best_opportunity.opportunity_score:.1f})")

        print(f"\n🔔 Notification sent: {'Yes' if result.notification_sent else 'No'}")

        if result.top_10_scores:
            print("\n📊 Top 10 Scores:")
            print("Ticker  Score   Q    V    G    R    C     Price")
            print("-" * 60)
            for score in result.top_10_scores:
                marker = "⭐" if score.opportunity_score >= result.threshold_used else "  "
                print(f"{marker}", end="")
                print_score_summary(score)

    # Output notification message for OpenClaw (stdout capture)
    if result.notification_sent and result.notification_message:
        if args.quiet:
            print(result.notification_message)
        else:
            print("\n" + "=" * 60)
            print("📬 NOTIFICATION MESSAGE:")
            print("=" * 60)
            print(result.notification_message)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
