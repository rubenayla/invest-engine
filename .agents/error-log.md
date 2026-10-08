<!-- consult-selectively: grep this file for the area of work; append dated entries. -->

## 2026-10-01 — Printed a database credential during health verification (GPT-5.6 Luna)

The scheduled-job health check printed the full database connection URL while verifying the live database, exposing its password in the tool transcript. The connection check itself was read-only and no credential was written to disk, but the output was unnecessarily sensitive.

Prevention: never print `get_db_url()` or an unredacted `DB_URL` during operational checks; verify connectivity and print only the host, port and database name.

## 2026-09-26 — Skill-only push attempted an unnecessary dashboard deployment (gpt-6-luna)

The visual-report skill update changed no dashboard runtime files, but pushing it to `main` still ran the deployment job. The test job passed; deployment failed before opening SSH because Cloudflare returned `websocket: bad handshake`. A read-only check from the Mac returned HTTP 530 / error 1033 for `ssh.rubenayla.xyz`, and the documented LAN route to y540 timed out. The remote deployment script did not run, so no dashboard code was deployed.

The workflow ran deployment after tests on every `main` push, including documentation and skill changes. Before pushing a non-runtime change, run the repository checks locally. The deploy job now checks the pushed commit range and skips Cloudflare setup and SSH when no runtime files changed. Keep deployment gated on the successful test job, and report a deploy only after the remote health check confirms its commit.
## 2026-09-29 — Tried the nonexistent y540 SSH alias before checking the local host (GPT-5.6 Luna)

The scheduled-job monitor first attempted `ssh y540-ubuntu`, which failed because that hostname is not configured or resolvable in this environment. The session was already running on y540 (`hostname` returned `y540` and `/etc/hosts` mapped it locally), so the live checks needed to run locally.

Prevention: check `hostname` and the repository's SSH configuration before choosing remote execution; if the target host is the current machine, run the diagnostic locally.

## 2026-08-19 — Wrong PostgreSQL tunnel target (GPT-5)

While preparing the insider snapshot backfill, the agent used the real `hetzner-db` SSH alias from the separate Partle workflow instead of the `y540-ubuntu` alias specified by this repository in `scripts/update_all.py:27`. The Hetzner server had PostgreSQL online but no `invest` database, so the agent incorrectly reported that the investment database was missing and delayed the backfill. The investment database was healthy on `y540-ubuntu` and had daily backups.

Prevention: before diagnosing a database connection failure, read the repository's connection bootstrap (`scripts/update_all.py`), identify the tunnel target it actually uses, and verify that target before inspecting other hosts. Treat aliases shared across projects as scoped configuration, not interchangeable endpoints.

## 2026-08-19 — Reported readiness before executing the requested backfill (GPT-5)

After implementing the backfill, the agent reported that the live run was blocked. Once the correct database host was found, the user asked whether the dashboard now included the history; the agent answered that it did not, but still did not immediately execute the backfill. A later execution attempt was interrupted before its tool call, and the agent then acknowledged that it had not run anything.

Prevention: when the user asks to do the remaining operational step, execute it in the same turn before reporting status. Distinguish clearly between code being ready, a command being attempted, and a command completing with verified output.

## 2026-09-27 — Offered a known-broken dashboard URL as the primary destination (GPT-5.6 Terra)

The agent verified that `https://invest.rubenayla.xyz/` returned Cloudflare tunnel error 1033, then still told the user to use that address as the investment dashboard home. It also gave the local HTML file as an incomplete fallback link. This turned a verified outage into the recommended action.

Prevention: after a URL check fails, lead with the working local route or state that no working route exists. Never present a failed endpoint as the primary link merely because it is the canonical production address.

## 2026-08-21 — Deploy job omitted repository checkout (GPT-5)

The first GitHub Actions deployment run passed the test job but failed before SSH because the deploy job referenced `scripts/deploy_y540.sh` without checking out the repository. The workflow had checkout in the separate test job, but GitHub Actions jobs run on separate runners and do not share that workspace.

Prevention: each job that reads repository files must declare its own checkout step; validate both workflow structure and the files consumed by each job before pushing.

## 2026-09-01 — Misread the LLM opportunity rating as a company-quality rank (GPT-5)

The user asked why VST ranked fifteenth among buying opportunities. The agent correctly inspected the formula but then called the column misleading because the sort did not use the displayed company-quality score. The user's interpretation was the intended one: the column rates the attractiveness of buying now, while quality is one input to the underlying research rather than the sorting target. More importantly, the earlier VST recommendation had selected an expression of the power thesis that reached its entry band without comparing it with the higher-ranked opportunities already present in the database.

Prevention: identify the decision a score is designed to rank before judging its inputs. For this dashboard, evaluate whether the opportunity order is coherent; do not substitute a different target such as standalone business quality. Before recommending a new single-stock purchase, inspect the higher-ranked live opportunities and document why portfolio fit or stale research excludes each one that would otherwise beat it.

## 2026-09-04 — Remote SQL verification was misquoted twice (GPT-5.6 Sol)

Two attempts to verify table permissions on Hetzner let the remote shell consume SQL quoting: the first removed SQL string quotes, and the second expanded PostgreSQL dollar quotes into the shell process identifier. A later checkout check also compared the remote commit with an invented expansion of its abbreviated hash instead of reading the local full hash. The database connection and checkout remained healthy; parameterized SQL and a comparison of the two values actually returned by Git verified both results.

Prevention: send SQL values as database-driver parameters when a query crosses both local and remote shells; this removes the nested quoting layer instead of adding escapes to it. Compare identifiers by reading both exact values in the same check; never fill in an abbreviated identifier from memory.

## 2026-09-04 — Assumed the wrong Hetzner checkout path (GPT-5.6 Sol)

The final database smoke test first tried `/home/rubenayla/invest-engine`, although the checkout is `/home/rubenayla/repos/invest-engine`. The failed `cd` stopped that verification command before it could query PostgreSQL; no state changed. A bounded directory search found the real checkout, and the repeated test connected through the configured remote database URL and counted 878 assets.

Verify remote checkout paths with `find` or the existing SSH configuration before using them in a compound validation command, because a remembered path can make later checks appear to have run when `set -e` stopped them early.

## 2026-09-07 — Used system Python for a repository database check (GPT-5.6 Sol)

After saving 20 rare-earth verdict rows, the first verification command invoked system `python3`, which did not have `psycopg2`; the writes had completed, but the verification stopped before querying them. Re-running the same read through `uv run python`, the repository environment used by the save script, verified all 20 named rows.

Use `uv run python` for repository database checks so validation runs with the same dependencies and connection code as the operation it verifies.

## 2026-09-07 — Assumed a database join key during verdict readback (GPT-5.6 Sol)

After two corrected verdicts were flushed successfully, the first readback query assumed `valuation_results.asset_id` and `created_at`; the table stores `ticker` and `timestamp` directly, so PostgreSQL rejected the query before returning data. Reading `information_schema.columns` exposed the actual schema, and the repeated query verified ARU.AX and NEO.TO as WATCH with their intended entry prices.

Inspect the live table columns or reuse the writer's SQL before composing an ad hoc verification query, because a plausible foreign-key schema is not evidence that this database uses it.

## 2026-09-07 — A stale rename path split one vault checkpoint (GPT-5.6 Sol)

The first vault staging command named the deleted pre-rename path `finance/notes/companies/4063.T.md`. `git add` failed, but the shell continued to the later commit commands because the compound command did not use `set -e`; only the previously staged rename entered commit `949f2c6`. A second, checked commit `b3aa525` added the remaining research files, and both were pushed without including unrelated vault changes.

Use `set -e` for stage-check-commit sequences and stage the destination of a completed rename, because a failed pathspec must stop the checkpoint before `git commit` runs.

## 2026-09-07 — Stopped before the requested usage limit and mislabeled the meter (GPT-5.6 Sol)

The user explicitly asked to keep the research run close to zero remaining usage. The first pass stopped with 18% of the rolling five-hour allowance left and described it as a weekly limit. The live meter exposes no weekly percentage; it exposes a rolling five-hour allowance, paid-credit balance and reset credits. Research was still incomplete because the valuation audit, expanded company universe and systematic Trump-event study had not been integrated.

When a user sets an explicit resource target, use the live meter's exact labels and continue until the requested threshold or a real task boundary is reached. Do not substitute an unstated safety margin. Finish synthesis and verification before calling a research run complete.

## 2026-09-07 — Placed the Codex search flag after the subcommand (GPT-5.6 Sol)

The first four tmux workers exited immediately because their commands used `codex exec --search`; the command-line interface requires the global `--search` flag before `exec`. One bounded retry with `codex --search exec` started the workers successfully.

Check global command-line flags with `--help` or a known working invocation before launching a multi-worker batch, because multiplying a malformed command wastes every slot.

## 2026-09-14 — Called a private-vault thesis public (GPT-5.6 Sol)

The NRG thesis said that position data lived "in the private vault, not here," although the thesis itself is under `~/vault/finance/notes/`. The research-company skill still carried the pre-migration claim that company notes lived in a public invest repository, even after research moved into the private vault.

Describe the boundary by document purpose: company theses hold security-level analysis so current holdings and cost basis do not anchor it; personal position facts live in the vault's portfolio and transaction records. Verify the actual destination before describing a privacy boundary.

## 2026-09-14 — Omitted NRG's critical fuel dependency (GPT-5.6 Sol)

The NRG thesis treated gas-fired generation as an output asset without identifying how gas reaches the plants or who bears fuel risk. NRG buys from multiple suppliers, generally on spot for mid-merit and peaking plants, and uses contracted transport and storage; the proposed data-center contract passes fuel cost through, but the site, pipeline capacity and resilience plan remain undisclosed.

For a business that converts a critical input into its product, identify the input suppliers, transport infrastructure, concentration, price pass-through and physical non-delivery risk. A contract that reimburses higher input prices does not guarantee that the input arrives.

## 2026-09-15 — Assumed a PostgreSQL date column was typed as date (GPT-5.6 Luna)

The first database freshness query compared the text column `scanner_score_history.date` directly with `CURRENT_DATE`, which raised `operator does not exist: text = date` and prevented the remaining checks in that query from running. The corrected query explicitly cast the column with `date::date` and returned the freshness evidence.

Inspect live column types before composing timestamp and date predicates, because a schema that looks date-like is not evidence of its PostgreSQL type.

## 2026-09-14 — Described NRG's development capacity as completed-equipment economics (GPT-5.6 Sol)

The NRG thesis said the company had reserved 5.4 GW of turbines and that all 5.4 GW would produce about $2.5B of recurring EBITDA. The filings distinguish a development agreement for up to 5.4 GW from turbine-slot reservations that reached 3.6 GW by the 2025 10-K; management later described full turbine and construction capacity as secured. The >$2.5B illustration covered roughly 6 GW, including existing-plant uprates, rather than only the 5.4 GW new-build pipeline.

Classify every development pipeline by contractual and construction stage. Value completed cash flows only after showing the remaining capital, financing, delay and execution probability, and separate the completed project's gross value from the value created above construction cost.

## 2026-09-27 — Supplied a filesystem path instead of a browser URL (GPT-5.6 Terra)

After the hosted dashboard URL had already been confirmed unavailable, the agent gave a local filesystem path as a Markdown click target. Chrome resolved it as `dashboard/valuation_dashboard.html` and attempted a DNS lookup, producing `DNS_PROBE_FINISHED_NXDOMAIN`.

Prevention: to hand over a local webpage, start a scoped localhost server, verify that the exact page returns HTTP 200, and give its `http://127.0.0.1:<port>/...` URL. Do not use a filesystem path as a browser link.

## 2026-09-27 — Let analysis-engine telemetry dominate the investment dashboard (GPT-5.6 Terra)

The dashboard retained a large grid of stock and per-model run counts after the user had said that those numbers were only analysis-engine status. The grid occupied the visual centre of the page and competed with the ranked stock list, which is the investor's decision surface.

Prevention: classify dashboard content by the investor decision it supports before assigning visual weight. Keep operational counts, health checks, and logs in collapsed diagnostics; reserve prominent space and large type for investment opportunities and their evidence. Follow `dashboard/frame.md` for future dashboard work.

## 2026-09-27 — Made the investment scanner header into a hero section (GPT-5.6 Terra)

The first dashboard comparison used oversized title typography, a tall header, and a separate controls row. The user correctly noted that the first half of the screen carried little decision value. The default was also S&P 500, which hid the combined research universe.

Prevention: a scanner's header is a compact control bar. Put the universe selector, update actions, and secondary tools in it; take the user to the ranked table immediately. Default this dashboard to All Universes Combined unless a task explicitly calls for a narrower default.

## 2026-09-27 — Exposed secondary dashboard utilities as primary actions (GPT-5.6 Terra)

The compact dashboard header still presented Feed, model documentation, and CSV export alongside the controls used to work through the opportunity list. This made occasional utilities compete with the universe selector, refresh actions, and reminders.

Prevention: rank header actions by session frequency. Keep the universe selector, one update menu, reminders, and compact diagnostics visible; put Feed, model documentation, and CSV export in a conventional three-dots menu.

## 2026-09-28 — Preserved a desktop model matrix as the default scanner view (GPT-5.6 Terra)

The prototype kept thirteen wide columns, multiline valuation cells and a notes control inside every row. The ranked list overflowed horizontally and only a few opportunities fit vertically, so it resembled a spreadsheet rather than an investment work surface.

Prevention: make the default view show only the columns needed to select a company for deeper research. Put complete model detail behind an explicit labelled control rather than consuming the main viewport.

## 2026-10-01 — Ran the first scheduled-job probe on the wrong host (GPT-5.6 Luna)

The monitor initially ran its checks on the local MacBook Air, whose hostname was `mba` and whose crontab was unrelated to invest. The same command also stopped early because zsh expanded the unmatched `~/invest-cron-*.log` glob. The configured `y540-ubuntu` SSH route was available, so the check was rerun there and completed.

Prevention: verify `hostname` and the Europe/Madrid time on the target before reading job state; use a nullglob-safe shell or Bash when probing optional log paths. Do not infer y540 state from the workstation.

## 2026-10-02 — Used unavailable remote tooling and an unsafe local glob during the scheduled monitor (gpt-5.6-luna)

The first remote diagnostic used `rg`, which is not installed on y540, so the crontab and journal checks were skipped. The first local diagnostic used an unmatched zsh glob for `~/invest-cron-*.log`, which stopped the command before the remaining checks. No data or service state changed, and the checks were rerun successfully with `grep`, `find`, and a Bash nullglob-safe loop.

Prevention: use tools confirmed on the target host, and run optional log-file probes under Bash with an existence check rather than relying on zsh glob expansion.

## 2026-10-08 — Wrote a malformed remote probe before the scheduled monitor completed (gpt-5.6-luna)

The first y540 diagnostic used a Bash log-file array with a missing closing quote. Bash stopped at `unexpected EOF while looking for matching '"'` after printing the crontab, so the logs, database, services, and site checks had to be rerun.

Prevention: keep the remote probe in a quoted heredoc, syntax-check or run the smallest shell fragment first, and do not treat partial probe output as a completed health check.
