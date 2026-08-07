# AI Tools Integration

The Investment Analysis Framework is designed to be **AI-controlled**. AI models like Claude and Gemini execute the entire research process autonomously using specialized tools.

## 🤖 Core Concept: AI Controls Everything

**Key Point**: The AI model (not the human) runs the analysis, interprets results, and performs research using the available tools.

- **Human Role**: Configure investment criteria in YAML files
- **AI Role**: Execute systematic screening, analyze results, perform deep-dive research, and generate recommendations

## Available AI Tool Categories

The framework provides three categories of tools that AI models can use:

### 1. 🔍 Systematic Screening Tools

**Location**: `src/invest/ai_tools/*/screening_tools.py`

AI models use these tools to:
- Execute systematic analysis pipelines on large stock universes
- Filter stocks based on quality, value, growth, and risk criteria
- Generate screening reports with pass/fail indicators
- Rank stocks by composite scores

**Example AI Workflow**:
```python
# AI model executes this automatically
run_screening_analysis(config="sp500_full.yaml", save_csv=True)
# Results: AI identifies 25-50 companies that pass all filters
```

### 2. 📊 Research and Analysis Tools  

**Location**: `src/invest/ai_tools/*/research_tools.py`

AI models use these tools to:
- Perform deep-dive analysis on companies that pass screening
- Gather additional financial data and metrics
- Analyze business models and competitive positioning
- Generate qualitative insights and research reports

**Example AI Workflow**:
```python
# AI model automatically researches promising candidates
analyze_company_fundamentals(ticker="GOOGL")
research_competitive_landscape(sector="Technology")  
generate_investment_thesis(company="Google")
```

### 3. 💼 Portfolio Construction Tools

**Location**: `src/invest/ai_tools/*/portfolio_tools.py`

AI models use these tools to:
- Build diversified portfolios from screened stocks
- Optimize position sizing and sector allocation
- Generate portfolio recommendations and reports
- Track portfolio performance and risk metrics

**Example AI Workflow**:
```python
# AI model constructs optimized portfolios
build_portfolio(filtered_stocks, target_size=20)
optimize_sector_allocation(portfolio, max_sector_weight=0.25)
generate_portfolio_report(portfolio)
```

## AI Integration Platforms

The framework integrates with two major AI platforms:

### Claude Desktop Integration

**Directory**: `src/invest/ai_tools/claude/`

**Available Tools**:
- `screening_tools.py` - Systematic analysis execution
- `research_tools.py` - Company research and analysis  
- `portfolio_tools.py` - Portfolio construction and optimization
- `data_tools.py` - Data gathering and processing

**AI Usage**: Claude models can directly access these tools through the Claude Desktop interface.

### Gemini AI Integration

**Directory**: `src/invest/ai_tools/gemini/`

**Available Tools**:
- `screening_tools.py` - Systematic analysis execution
- `research_tools.py` - Company research and analysis
- `portfolio_tools.py` - Portfolio construction and optimization  
- `data_tools.py` - Data gathering and processing

**AI Usage**: Gemini models can access these tools through the Gemini AI platform.

## Complete AI-Controlled Workflow

Here's how an AI model would typically use this framework:

### Step 1: AI Runs Systematic Screening

```bash
# AI model executes systematic analysis
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_top100.yaml --save-csv

# AI automatically:
# - Fetches S&P 500 stock data
# - Applies quality, value, growth, risk filters
# - Generates screening results with pass/fail indicators
# - Identifies 20-40 companies that meet all criteria
```

### Step 2: AI Analyzes Screening Results

```python
# AI model automatically:
# 1. Reads the generated CSV file
# 2. Identifies stocks that passed all filters (Passes_Filters = Y)
# 3. Ranks them by composite score
# 4. Selects top candidates for deep-dive analysis
```

### Step 3: AI Performs Deep Research

For each promising candidate, the AI model:
- Uses research tools to gather additional data
- Analyzes business model and competitive position
- Evaluates management quality and strategy
- Assesses industry trends and growth prospects
- Generates investment thesis for each company

### Step 4: AI Constructs Portfolio

Finally, the AI model:
- Uses portfolio tools to build diversified portfolios
- Optimizes sector allocation and position sizing
- Considers correlation and risk factors
- Generates final investment recommendations

## Key Advantages of AI Control

### 🎯 **Objective Analysis**
- AI eliminates human emotional bias and confirmation bias
- Consistent methodology applied to every stock
- No cherry-picking of favorable data

### ⚡ **Scale and Speed**
- AI can systematically analyze 500+ stocks in minutes
- Deep-dive analysis on 20-50 companies in hours
- Human would need weeks for equivalent analysis

### 🔄 **Reproducible Process**
- AI follows identical methodology every time
- Results are consistent and comparable across time periods
- No human inconsistencies or varying approaches

### 🧠 **Comprehensive Research**
- AI can simultaneously consider dozens of factors
- Perfect recall of all relevant information
- No human memory limitations or oversight

## Getting Started with AI Tools

### For AI Models (Claude, Gemini, etc.)

1. **Access the Framework**: Clone the repository and install dependencies
2. **Choose Configuration**: Select or create YAML configuration file
3. **Execute Screening**: Run systematic analysis pipeline
4. **Analyze Results**: Interpret screening output and identify candidates
5. **Perform Research**: Use research tools for deep-dive analysis
6. **Build Portfolio**: Use portfolio tools for final recommendations

### For Humans

1. **Set Investment Criteria**: Define screening parameters in YAML files
2. **Configure AI Environment**: Set up Claude Desktop or Gemini integration
3. **Provide AI Context**: Share this documentation with your AI model
4. **Let AI Execute**: Allow AI to run the complete research workflow
5. **Review Results**: Examine AI-generated analysis and recommendations

## Detailed Example Prompts

### 🎯 **Stock Screening Prompts**

**Basic Value Screening:**
```
I want to find undervalued quality stocks. Please screen the S&P 500 using conservative value criteria and show me the top 15 opportunities. For each stock, explain why it passed the filters and what makes it attractive.
```

**Growth Stock Analysis:**
```
I'm looking for high-quality growth stocks that aren't too expensive. Please run the analysis and identify technology companies with strong growth but reasonable valuations.
```

**International Opportunities:**
```
Warren Buffett has been investing in Japan recently. Please analyze Japanese stocks using the buffett_favorites configuration and explain why these companies represent good value compared to US stocks.
```

**Sector-Specific Analysis:**
```
I want to invest in healthcare but need help finding the best opportunities. Please screen healthcare stocks and recommend companies with strong competitive moats and reasonable prices.
```

### 📊 **Deep Analysis Prompts**

**Individual Stock Analysis:**
```
I'm considering investing in Apple (AAPL). Please run it through your systematic analysis and give me a detailed breakdown:
- Does it pass your quality, value, growth, and risk filters?
- What are its key strengths and weaknesses?
- How does it compare to other technology stocks?
- What's your investment recommendation?
```

**Comparative Analysis:**
```
Please compare Google (GOOGL) vs Microsoft (MSFT) using your systematic screening. Which one offers better value right now and why? Consider quality metrics, valuation, growth prospects, and risks.
```

**Market Analysis:**
```
I'm trying to decide between US and international markets. Please analyze both S&P 500 and Japanese TOPIX stocks and tell me:
- Which market offers better value opportunities?
- What are the key differences in quality and growth?
- Should I diversify internationally or focus on US stocks?
```

### 💼 **Portfolio Construction Prompts**

**Build Diversified Portfolio:**
```
Please build me a diversified portfolio of 20 stocks for long-term investing. I want:
- High-quality companies with strong competitive moats
- Reasonable valuations (not overpaying for growth)
- Good sector diversification
- Mix of US and international stocks
- Focus on companies with sustainable competitive advantages

For each recommendation, explain why you selected it.
```

**Value-Focused Portfolio:**
```
I follow a value investing approach similar to Warren Buffett. Please create a portfolio of 12-15 stocks that:
- Trade below intrinsic value with margin of safety
- Have predictable business models
- Generate strong free cash flows
- Have competitive advantages (moats)
- Include some of Buffett's recent international picks
```

**Conservative Income Portfolio:**
```
I need a conservative portfolio focused on dividend income and capital preservation. Please find:
- Dividend-paying stocks with sustainable payouts
- Companies with strong balance sheets and low debt
- Businesses in defensive sectors
- International diversification for currency hedging
- Focus on quality over growth
```

### 🔍 **Research and Analysis Prompts**

**Industry Deep Dive:**
```
I'm interested in the semiconductor industry. Please analyze the key players using your screening tools and tell me:
- Which companies have the strongest competitive positions?
- Who offers the best value at current prices?
- What are the key risks and opportunities in the sector?
- Should I invest in chip manufacturers or equipment makers?
```

**Economic Analysis:**
```
With current market conditions, please analyze what your screening reveals about:
- Which sectors are showing the best opportunities?
- Are growth or value stocks more attractive right now?
- How do US opportunities compare to international markets?
- What does the data suggest about overall market valuation?
```

**Risk Assessment:**
```
Please run the risk screening and identify:
- Stocks with high debt levels that might be concerning
- Companies with declining business fundamentals
- Overvalued stocks that investors should avoid
- Sectors or regions with elevated risk levels
```

### 📈 **Follow-up and Monitoring Prompts**

**Portfolio Review:**
```
I own [list of stocks]. Please run each through your current analysis and tell me:
- Which ones still meet your investment criteria?
- Have any deteriorated significantly since I bought them?
- Are there better alternatives I should consider?
- Should I rebalance or make any changes?
```

**Market Updates:**
```
Please re-run your S&P 500 analysis and compare it to your previous screening. What's changed?
- Are there new opportunities that have emerged?
- Have any of your top picks become less attractive?
- How has overall market quality and valuation shifted?
```

**Specific Stock Updates:**
```
I'm holding Tesla (TSLA) which previously failed your filters. Has anything improved? Please re-analyze and tell me if the investment thesis has changed or if I should still avoid it.
```

## Example AI Conversation Flow

**Human**: "Please analyze the S&P 500 and find the best value stocks using conservative criteria."

**AI Response**:
1. "I'll run systematic screening on the S&P 500 using conservative value criteria..."
2. *AI executes screening tools*
3. "Found 23 companies that passed all filters. Now performing deep-dive analysis on top candidates..."
4. *AI uses research tools on promising stocks*
5. "Based on my analysis, here are the top 10 value opportunities with detailed investment theses..."
6. *AI uses portfolio tools to create diversified recommendations*

**Human**: "Tell me more about the top 3 picks and why they're attractive."

**AI Response**:
*AI provides detailed analysis of each company, including financial metrics, business model, competitive advantages, and valuation rationale*

**Human**: "How do these compare to international opportunities?"

**AI Response**:
1. "Let me analyze Japanese and European markets using the international configurations..."
2. *AI runs international screening*
3. "Interesting - I found several Japanese companies trading at significant discounts to US equivalents..."
4. *AI provides comparative analysis and diversification recommendations*

## Advanced AI Capabilities

### Multi-Modal Analysis
- AI can process both quantitative data (financial metrics) and qualitative information (news, reports)
- Combines systematic screening with conversational analysis
- Generates comprehensive investment research

### Dynamic Configuration
- AI can adjust screening criteria based on market conditions
- Optimize parameters for different investment styles (value, growth, quality)
- Create custom configurations for specific investment themes

### Continuous Monitoring
- AI can re-run analysis periodically to track changes
- Monitor portfolio performance and suggest adjustments
- Alert to significant changes in screened companies

## Next Steps

- **[Basic Screening Tutorial](basic-screening.md)** - Learn the systematic screening process
- **[Custom Configurations](custom-configurations.md)** - Create custom investment criteria
- **[Understanding Results](../user-guide/understanding-results.md)** - Interpret AI-generated analysis
- **[API Reference](../api-reference/pipeline.md)** - Technical details for AI integration

---

**Remember**: This framework is designed to empower AI models to perform comprehensive investment research autonomously. The AI controls the entire process from screening to final recommendations.