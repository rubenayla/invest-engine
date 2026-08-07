# Repository Organization Rules

**CRITICAL**: The repository root must stay clean and organized at all times.

## .claude/ Folder Purpose

The `.claude/` folder contains **ONLY persistent project knowledge**:
- ✅ Workflows and procedures (e.g., `debugging_workflow.md`)
- ✅ Project standards and rules (e.g., `organization_rules.md`)
- ✅ Reusable command templates in `/commands/` subdirectory
- ❌ **NEVER store session-specific notes** - those stay in conversation context

**Why no session files?** Session context is already managed by the conversation system. Creating temporary files here would just be clutter.

## What Belongs in Root
✅ **Configuration files only:**
- `pyproject.toml` - Python project config
- `uv.lock` - Dependency lock file
- `mkdocs.yml` - Documentation config
- `.gitignore`, `.gitattributes` - Git config
- `.python-version` - Python version specification

✅ **Documentation files only:**
- `README.md` - Main project documentation
- `CLAUDE.md` - Claude-specific instructions
- `PROJECT.md` - Project overview
- `MODEL_MANAGEMENT.md` - Model management docs
- `MULTI_HORIZON_NN.md` - Neural network docs
- `MCP_USAGE.md` - MCP server documentation

✅ **Directories only:**
- `src/` - Source code
- `tests/` - Test files
- `scripts/` - Executable scripts
- `data/` - Data files (cache, databases)
- `logs/` - All log files
- `docs/` - Extended documentation
- `dashboard/` - Dashboard HTML/JS/CSS
- `models/` - ML models (neural_network/, backtesting/, autoresearch/)

- `infra/` - Infrastructure configs (grafana/)
- `config/` - Configuration files
- `~/vault/finance/notes/` - Research notes (live in the private vault, not this repo)
- `reports/` - Generated reports
- `old_artifacts/` - Archived old code
- `.claude/` - Claude memory/notes
- `.github/` - GitHub Actions workflows
- `.venv/` - Virtual environment (gitignored)
- `.cache/`, `.pytest_cache/`, `.ruff_cache/` - Tool caches (gitignored)
- `htmlcov/` - Coverage reports (gitignored)

## What Does NOT Belong in Root

❌ **NEVER create these in root:**
- Temporary JSON files (`data_fetch_summary_*.json`) → Move to `logs/`
- Coverage files (`.coverage`, `coverage.xml`) → Move to `htmlcov/`
- Log files (`*.log`) → Move to `logs/`
- Cache files (`*.pkl`, `*.cache`) → Move to `data/` or appropriate subdirectory
- Temporary scripts (`temp_*.py`, `test_*.py`) → Move to `/tmp/` or delete after use
- Model files (`*.pth`, `*.pt`) → Move to `models/neural_network/models/`
- Data files (`*.csv`, `*.json` with data) → Move to `data/`
- Debugging files → Move to `.claude/` if needed for memory, otherwise delete

## Cleanup Checklist

Before finishing any work session:
1. Check root: `ls -la | grep -v "^d" | grep -v "^\."`
2. Move temporary files to appropriate directories
3. Delete any unused temporary files
4. Verify no new clutter was introduced

## Historical Context

Last week (commit ab0fe64 era), the repository became disorganized with:
- Temporary files left in root
- Log files scattered across directories
- No clear organization standards
- Files created without considering proper location

**This must NEVER happen again.**

## Enforcement

When Claude creates ANY file:
1. First determine proper location based on file type
2. NEVER default to root directory
3. If unsure, ask user or use `/tmp/` for temporary files
4. For Claude's memory/notes, ALWAYS use `.claude/` directory
