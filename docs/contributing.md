# Documentation

This directory contains the source files for the Systematic Investment Analysis Framework documentation, built with [MkDocs](https://www.mkdocs.org/) and the [Material theme](https://squidfunk.github.io/mkdocs-material/).

## Development

### Prerequisites

Install documentation dependencies:

```bash
uv sync --group docs
```

### Local Development

Start the documentation server:

```bash
uv run mkdocs serve
```

Then open http://localhost:8000 in your browser. The site will automatically reload when you make changes.

### Building

Build the static site:

```bash
uv run mkdocs build
```

The built site will be available in the `site/` directory.

## Deployment

Documentation is automatically deployed to GitHub Pages when changes are pushed to the `main` branch.

### Manual Deployment

You can also deploy manually:

```bash
uv run mkdocs gh-deploy
```

This will build the documentation and push it to the `gh-pages` branch.

## Structure

```
docs/
├── index.md                    # Home page
├── getting-started/           # Installation and setup
│   ├── installation.md
│   ├── quickstart.md
│   └── configuration.md
├── user-guide/               # Comprehensive usage guide
│   ├── overview.md
│   ├── running-analysis.md
│   ├── understanding-results.md
│   ├── configuration-options.md
│   └── output-formats.md
├── developer-guide/          # Extending the framework
│   ├── architecture.md
│   ├── pipeline-components.md
│   ├── adding-screeners.md
│   ├── data-providers.md
│   └── extending.md
├── api-reference/           # Technical documentation
│   ├── pipeline.md
│   ├── screening.md
│   ├── data.md
│   └── configuration.md
└── tutorials/              # Step-by-step guides
    ├── basic-screening.md
    ├── custom-configurations.md
    ├── sp500-analysis.md
    └── ai-tools.md
```

## Writing Guidelines

### Style

- Use clear, concise language
- Include code examples for technical concepts
- Add diagrams for complex workflows (using Mermaid)
- Use admonitions (tips, warnings, notes) appropriately

### Code Examples

Always include full, runnable examples with `uv run`:

```bash
# ✅ Good
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv

# ❌ Bad
python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv
```

### Admonitions

Use admonitions to highlight important information:

```markdown
!!! tip "Performance"
    The full S&P 500 analysis takes 10-15 minutes.

!!! warning "Important"
    Always use `uv run` for all commands.

!!! note "Background"
    This explains the reasoning behind a design decision.
```

### Cross-References

Link between documentation sections:

```markdown
See the [Configuration Guide](../getting-started/configuration.md) for details.
```

## Contributing

1. Check existing documentation for similar content
2. Follow the established structure and style
3. Test locally with `mkdocs serve`
4. Submit a pull request with your changes

The documentation will be automatically deployed when merged to `main`.