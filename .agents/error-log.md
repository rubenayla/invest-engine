<!-- consult-selectively: grep this file for the area of work; append dated entries. -->

## 2026-08-19 — Wrong PostgreSQL tunnel target (GPT-5)

While preparing the insider snapshot backfill, the agent used the real `hetzner-db` SSH alias from the separate Partle workflow instead of the `y540-ubuntu` alias specified by this repository in `scripts/update_all.py:27`. The Hetzner server had PostgreSQL online but no `invest` database, so the agent incorrectly reported that the investment database was missing and delayed the backfill. The investment database was healthy on `y540-ubuntu` and had daily backups.

Prevention: before diagnosing a database connection failure, read the repository's connection bootstrap (`scripts/update_all.py`), identify the tunnel target it actually uses, and verify that target before inspecting other hosts. Treat aliases shared across projects as scoped configuration, not interchangeable endpoints.

## 2026-08-19 — Reported readiness before executing the requested backfill (GPT-5)

After implementing the backfill, the agent reported that the live run was blocked. Once the correct database host was found, the user asked whether the dashboard now included the history; the agent answered that it did not, but still did not immediately execute the backfill. A later execution attempt was interrupted before its tool call, and the agent then acknowledged that it had not run anything.

Prevention: when the user asks to do the remaining operational step, execute it in the same turn before reporting status. Distinguish clearly between code being ready, a command being attempted, and a command completing with verified output.
