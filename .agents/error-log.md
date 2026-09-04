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

Two attempts to verify table permissions on Hetzner let the remote shell consume SQL quoting: the first removed SQL string quotes, and the second expanded PostgreSQL dollar quotes into the shell process identifier. The database connection itself remained healthy, and a parameterized third query verified the intended permissions.

Prevention: send SQL values as database-driver parameters when a query crosses both local and remote shells; this removes the nested quoting layer instead of adding escapes to it.
