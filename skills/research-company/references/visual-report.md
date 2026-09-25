# Visual company report

Create one self-contained HTML page per researched company at
`~/vault/finance/notes/companies/{TICKER}/visual-report.html`. Create the ticker
folder when needed. This is the visual companion to the Markdown thesis, not a
replacement for it. Keep the page useful when opened locally: inline its styles,
data and JavaScript, use no remote libraries, and do not require a build step.

## Page structure

Start with a compact company identity, a link to TIKR, and one collapsible
“Dates & sources” item. Put all report, market-price and financial-statement
dates in that item. Do not scatter freshness timestamps elsewhere.

At the top, give a very short plain-English account of what the company sells
and who pays, followed by its stated 3–5 year plan. Then show the business
snapshot: the most useful valuation measures (usually trailing P/E and, when
available, forward P/E), revenue, gross margin, operating profit and margin,
net income, free cash flow, total assets, liabilities and book equity. Show
units and period/basis beside each figure. Use reported figures and label
adjusted figures separately. When a ratio or figure is unavailable or not
meaningful, say so instead of inventing a substitute.

Keep opportunities and risks short. Each item links to its fuller explanation
in a detail section lower on the same page. Put definitions, calculations and
source links in a compact lower section. Cite the filing or company release
that supports each material figure; link valuation assumptions to their source
and state their date.

## Financial history charts

Use four aligned panels, in a two-column layout on wide screens and one column
on narrow screens:

1. **Balance sheet, at date:** assets, liabilities and book equity.
2. **Revenue & profit, trailing 12 months:** revenue, gross profit, reported
   operating profit and net income.
3. **Cash flow, trailing 12 months:** operating cash flow and free cash flow.
4. **Margins, trailing 12 months:** gross, operating and net margins, plus
   operating- and free-cash-flow margins when their source data is available.

Keep cash-flow lines out of the revenue-and-profit chart, and keep percentage
series in their own panel so the amount lines remain easy to compare. Order
dates chronologically and space them by elapsed time; show annual and quarterly
observations together when both are available, with a subtle vertical guide at
each year. Use the same periods and selected-period marker across panels. Put
the updating values in one horizontal row above each chart, not a grid of cards.

Use a consistent colour for a measure across amount and margin views where
possible. Make legend entries control line visibility. Hovering or focusing a
series should emphasize its line, points and legend label together. Give each
axis a clear unit. Fit the scale to the data with enough headroom; do not force
margin axes to 100%. Include tooltips or an equivalent accessible way to read
the exact date and value.

## Source and calculation rules

Use the latest primary financial filings available for the report cutoff.
Record the financial period end, filing date and source URL for each plotted
observation. Use the company's reporting currency and identify it on every
amount chart. Do not mix currencies within a series.

Balance-sheet values are point-in-time balances. Flow measures are trailing
12-month totals when sufficient filings support the calculation. For interim
periods, calculate trailing 12 months as prior full-year amount plus current
year-to-date amount minus prior-year year-to-date amount. Derive free cash flow
as operating cash flow minus capital expenditure only when both inputs have a
consistent period and definition; disclose the formula. Compute each margin as
its matching trailing 12-month flow divided by trailing 12-month revenue. Do
not substitute adjusted measures for reported statements without a separate
label.

Map each issuer's facts to its reported financial statements and check the
calculation against the filing. XBRL tag names can vary by company and industry;
never assume a tag is comparable without checking its definition. Leave a gap
where a value is missing rather than plotting zero or carrying an older value
forward. Omit a series when the source does not support it. Explain any
important comparability break, restatement or non-standard fiscal year.

## Verification

Before saving, check that:

- the page opens as a local file and its charts render without external assets;
- each visible chart line appears once in its legend and in the matching value
  row, with no cash-flow series in the revenue-and-profit panel;
- plotted amounts, periods, units and formulas match the source statements;
- opportunity and risk links reach their detailed explanations;
- the dates appear in one place, and the layout remains readable on a phone.

Never backfill every old company report as part of an ordinary research run.
Generate or refresh a company's visual report when that company's research is
being written or materially refreshed, so the visual and thesis do not imply
different research dates.
