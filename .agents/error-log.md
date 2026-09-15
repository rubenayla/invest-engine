<!-- consult-selectively: grep this file for the area of work; append dated entries. -->

## 2026-08-19 — Wrong PostgreSQL tunnel target (GPT-5)

While preparing the insider snapshot backfill, the agent used the real `hetzner-db` SSH alias from the separate Partle workflow instead of the `y540-ubuntu` alias specified by this repository in `scripts/update_all.py:27`. The Hetzner server had PostgreSQL online but no `invest` database, so the agent incorrectly reported that the investment database was missing and delayed the backfill. The investment database was healthy on `y540-ubuntu` and had daily backups.

Prevention: before diagnosing a database connection failure, read the repository's connection bootstrap (`scripts/update_all.py`), identify the tunnel target it actually uses, and verify that target before inspecting other hosts. Treat aliases shared across projects as scoped configuration, not interchangeable endpoints.

## 2026-08-19 — Reported readiness before executing the requested backfill (GPT-5)

After implementing the backfill, the agent reported that the live run was blocked. Once the correct database host was found, the user asked whether the dashboard now included the history; the agent answered that it did not, but still did not immediately execute the backfill. A later execution attempt was interrupted before its tool call, and the agent then acknowledged that it had not run anything.

Prevention: when the user asks to do the remaining operational step, execute it in the same turn before reporting status. Distinguish clearly between code being ready, a command being attempted, and a command completing with verified output.

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
