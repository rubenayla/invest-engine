"""
Telegram Notification Formatter for Opportunity Scanner

Formats opportunity scores into visual Telegram messages with bar graphs.
"""

from typing import Optional
from .scoring_engine import OpportunityScore


class TelegramNotifier:
    """
    Format opportunity scores for Telegram notifications.

    Output format:
    ```
    TICKER - Company Name
    ═══════════════════════════
    OPPORTUNITY SCORE: 78/100

    • Quality:  72  ████████░░
    • Value:    85  █████████░
    • Growth:   68  ███████░░░
    • Risk:     80  ████████░░
    • Catalyst: 75  ████████░░

    Valuation:
      Current: $45.20
      DCF: $58.00 (+28%)
      RIM: $52.00 (+15%)

    Key: P/E 14 | ROE 18% | D/E 0.4

    Threshold today: 75/100
    ```
    """

    # Bar graph characters
    FILLED = '█'
    EMPTY = '░'
    BAR_WIDTH = 10

    def __init__(self):
        pass

    def _score_to_bar(self, score: float) -> str:
        """Convert score (0-100) to visual bar."""
        filled = int(score / 100 * self.BAR_WIDTH)
        empty = self.BAR_WIDTH - filled
        return self.FILLED * filled + self.EMPTY * empty

    def _format_upside(self, current: float, fair_value: Optional[float]) -> str:
        """Format fair value with upside percentage."""
        if not fair_value or current <= 0:
            return "N/A"

        upside = (fair_value - current) / current * 100
        sign = '+' if upside >= 0 else ''
        return f"${fair_value:.2f} ({sign}{upside:.0f}%)"

    def _format_metric(self, value: Optional[float], suffix: str = '', decimals: int = 1) -> str:
        """Format a metric value for display."""
        if value is None:
            return "N/A"
        if decimals == 0:
            return f"{int(value)}{suffix}"
        return f"{value:.{decimals}f}{suffix}"

    def format_notification(
        self,
        score: OpportunityScore,
        threshold: float,
        is_exceptional: bool = False
    ) -> str:
        """
        Format a complete notification message.

        Parameters
        ----------
        score : OpportunityScore
            The opportunity score to format
        threshold : float
            Current notification threshold
        is_exceptional : bool
            Whether this is an exceptional opportunity (>90)

        Returns
        -------
        str
            Formatted Telegram message
        """
        lines = []

        # Header with emoji indicator
        if is_exceptional:
            lines.append(f"🌟 **[{score.ticker}](https://finance.yahoo.com/quote/{score.ticker})** - {score.company_name}")
        else:
            lines.append(f"📊 **[{score.ticker}](https://finance.yahoo.com/quote/{score.ticker})** - {score.company_name}")

        lines.append("═" * 30)

        # Main score with emoji
        score_emoji = "🔥" if score.opportunity_score >= 85 else "📈"
        lines.append(f"{score_emoji} OPPORTUNITY SCORE: {score.opportunity_score:.0f}/100")
        lines.append("")

        # Component breakdown with bars
        components = [
            ("Quality", score.quality_score),
            ("Value", score.value_score),
            ("Growth", score.growth_score),
            ("Risk", score.risk_score),
            ("Catalyst", score.catalyst_score),
        ]

        for name, value in components:
            bar = self._score_to_bar(value)
            lines.append(f"• {name:9} {value:4.0f}  {bar}")

        lines.append("")

        # Valuation section
        lines.append("💰 Valuation:")
        lines.append(f"  Current: ${score.current_price:.2f}")

        if score.dcf_fair_value:
            dcf_str = self._format_upside(score.current_price, score.dcf_fair_value)
            lines.append(f"  DCF: {dcf_str}")

        if score.rim_fair_value:
            rim_str = self._format_upside(score.current_price, score.rim_fair_value)
            lines.append(f"  RIM: {rim_str}")

        if score.ensemble_fair_value:
            ens_str = self._format_upside(score.current_price, score.ensemble_fair_value)
            lines.append(f"  Ensemble: {ens_str}")

        lines.append("")

        # Key metrics one-liner
        km = score.key_metrics
        key_parts = []

        pe = km.get('pe')
        if pe is not None and pe > 0:
            key_parts.append(f"P/E {pe:.0f}")

        roe = km.get('roe')
        if roe is not None:
            key_parts.append(f"ROE {roe:.0f}%")

        de = km.get('debt_equity')
        if de is not None:
            de_ratio = de / 100 if de > 5 else de
            key_parts.append(f"D/E {de_ratio:.1f}")

        if key_parts:
            lines.append(f"🔑 Key: {' | '.join(key_parts)}")

        lines.append("")

        # Footer with threshold context
        lines.append(f"📅 Threshold today: {threshold:.0f}/100")
        lines.append("")
        lines.append(f"🔎 [More Info](https://finance.yahoo.com/quote/{score.ticker})")

        return "\n".join(lines)

    def format_no_opportunities(self, threshold: float, best_score: Optional[float]) -> str:
        """
        Format a message when no opportunities meet the threshold.

        Parameters
        ----------
        threshold : float
            Current notification threshold
        best_score : float, optional
            Best score seen today

        Returns
        -------
        str
            Formatted message (for logging, not typically sent)
        """
        lines = [
            "📊 Daily Scanner Summary",
            "═" * 30,
            f"No opportunities above threshold today.",
            "",
            f"📅 Threshold: {threshold:.0f}/100",
        ]

        if best_score:
            lines.append(f"📈 Best score: {best_score:.0f}/100")

        return "\n".join(lines)

    def format_weekly_summary(
        self,
        notifications_sent: int,
        top_scores: list,
        avg_threshold: float,
        current_threshold: float
    ) -> str:
        """
        Format a weekly summary message.

        Parameters
        ----------
        notifications_sent : int
            Number of notifications sent this week
        top_scores : list
            List of (ticker, score) tuples for top opportunities
        avg_threshold : float
            Average threshold over the week
        current_threshold : float
            Current threshold value

        Returns
        -------
        str
            Formatted weekly summary
        """
        lines = [
            "📊 Weekly Scanner Summary",
            "═" * 30,
            "",
            f"📬 Notifications sent: {notifications_sent}",
            f"📅 Avg threshold: {avg_threshold:.0f}/100",
            f"📍 Current threshold: {current_threshold:.0f}/100",
            "",
        ]

        if top_scores:
            lines.append("🏆 Top opportunities this week:")
            for ticker, score in top_scores[:5]:
                lines.append(f"  • {ticker}: {score:.0f}")

        return "\n".join(lines)

    def format_alert_message(self, message: str) -> str:
        """
        Format a simple alert message for OpenClaw.

        Parameters
        ----------
        message : str
            The notification content

        Returns
        -------
        str
            The same message (passthrough for OpenClaw)
        """
        return message
