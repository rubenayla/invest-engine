# Installation

## Prerequisites

- **Python 3.8+** - The framework requires Python 3.8 or later
- **UV** - For dependency management
- **Git** - For cloning the repository

## Installing UV

If you don't have UV installed:

=== "Linux/macOS/WSL"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Windows PowerShell"

    ```powershell
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "Alternative (pip)"

    ```bash
    pip install uv
    ```

!!! tip "Path Configuration"
    After installing UV, you may need to add it to your PATH. Follow the instructions shown in the installation output.

## Clone and Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/rubenayla/invest-engine.git
   cd invest
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Verify installation**:
   ```bash
   uv run python scripts/systematic_analysis.py --help
   ```

## Optional: Documentation Development

If you want to work on documentation:

```bash
# Install documentation dependencies
uv sync --group docs

# Start documentation server
uv run mkdocs serve
```

## Verification

Test that everything works:

```bash
# Run a simple analysis
uv run python scripts/systematic_analysis.py dashboard/configs/test_tech_giants.yaml --save-csv

# Check if results were generated
ls *.csv
```

If you see a CSV file generated, you're ready to go!

## Troubleshooting

### Common Issues

**UV not found**
: Make sure UV is in your PATH. You may need to restart your terminal or add UV's bin directory to your PATH manually.

**Python version conflicts**
: The framework requires Python 3.8+. Check your version with `python --version` or `python3 --version`.

**Permission errors**
: On some systems, you may need to use `python3` instead of `python`, or run with appropriate permissions.

### Getting Help

If you encounter issues:

1. Check the [troubleshooting section](../user-guide/troubleshooting.md)
2. Review existing [GitHub issues](https://github.com/rubenayla/invest-engine/issues)
3. Create a new issue with detailed error information

## 🤖 Ready to Use with AI

Once installed, you can instruct your AI assistant to use the framework. Here are example prompts to get started:

### Example AI Prompts

**Basic Stock Screening:**
```
I have this investment analysis framework installed. Please screen the S&P 500 for quality value stocks and show me the top 10 opportunities. Use conservative criteria.
```

**International Analysis:**
```
Please analyze Warren Buffett's favorite Japanese stocks using the japan_buffett_favorites configuration. I want to understand why Berkshire invested in Japanese trading houses.
```

**Specific Stock Analysis:**
```
Can you run the systematic screening and then analyze Apple (AAPL) in detail? Tell me if it passes the filters and what concerns you might have about the stock.
```

**Custom Research:**
```
I'm looking for undervalued technology stocks with strong growth. Please run the analysis and identify companies that might be good long-term investments.
```

**Comparative Analysis:**
```
Please compare the top US stocks (S&P 500) vs Japanese opportunities (TOPIX 30) and tell me which market offers better value right now.
```

### How AI Uses the Framework

The AI will automatically:
1. **Run systematic screening** using the appropriate configuration files
2. **Analyze the results** to identify opportunities and concerns
3. **Provide detailed insights** on individual companies
4. **Generate investment recommendations** based on the data
5. **Answer follow-up questions** about specific stocks or strategies

### AI-Controlled Workflow

Your AI assistant can execute the complete investment research process:
- Screen hundreds of stocks systematically
- Identify companies that pass quality, value, growth, and risk filters
- Perform deep-dive analysis on promising candidates
- Generate comprehensive investment reports
- Answer questions about specific companies or strategies

## Next Steps

- [Quick Start Guide](quickstart.md) - Run your first analysis
- [Configuration](configuration.md) - Customize screening criteria
- [AI Tools Tutorial](../tutorials/ai-tools.md) - Learn how AI controls the framework