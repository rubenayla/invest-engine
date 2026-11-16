# Investment dashboard frame

The dashboard helps an investor decide what deserves attention now. Its first
screen is for opportunities, not for proving that the analysis engine ran.

## Information order

1. Put the ranked stock list and the signals that affect a buy, watch, or pass
   decision first.
2. Keep filters, freshness, and actions nearby when they change that decision.
3. Put model coverage, run counts, database health, and logs in a collapsed
   diagnostic section. Keep them available for troubleshooting, but never use
   them as headline cards or a large table.

## Visual character

Use a quiet editorial layout: warm neutral background, dark green text,
restrained borders, and generous space around the page's main decision tool.
Large type is evidence of importance. Reserve it for a company, a decision,
or a material investment signal; never use it for process telemetry.

The scanner can be dense because comparison matters, but each row must remain
easy to scan. Prefer plain labels, compact values, and small status treatments
over decorative cards. Both light and dark system appearances must preserve
this hierarchy and contrast.

## Guardrails

Do not add a dashboard element merely because data exists. State the investor
question it answers, place it at the corresponding level of the hierarchy, and
hide operational detail unless it is needed to diagnose the system.

## Mobile and phone interface

On phones, design for one-handed thumb interaction and focused single-panel reading:

1. **Bottom thumb-zone navigation**: The primary navigation and main action buttons (switching between the 5 analysis views and toggling the stock universe drawer) sit at the bottom of the screen, where fingers comfortably reach them without stretching to the top.
2. **Whole screen or nothing**: On narrow viewports, the stock directory drawer occupies the full screen (or an 88% width drawer over a frosted dark backdrop) rather than an awkward desktop side-by-side split. When closed, it disappears completely.
3. **Backdrop dismissal**: Tapping the empty/dimmed area to the right of any open drawer or sheet immediately dismisses it.
4. **No touch-triggered hover tooltips**: Suppress mouse hover tooltips on touch devices (`@media (hover: none)`); taps must select or activate controls directly without spawning stranded desktop cards.
5. **Three-dot overflow for secondary links**: Secondary external research links (TIKR, Yahoo Finance, Google Finance, TradingView, SEC filings) tuck cleanly into a single `⋮` menu rather than cluttering the header.
