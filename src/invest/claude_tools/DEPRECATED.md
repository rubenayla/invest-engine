# DEPRECATED: Old Claude Tools

This directory contains the original Claude Desktop tools that are now deprecated.

## New Location

All AI tools have been moved to the new unified structure:

```
src/invest/ai_tools/
├── core/       # Shared business logic
├── claude/     # Claude Desktop tools (NEW)
└── gemini/     # Gemini tools (NEW)
```

## Migration

The tools in this directory (`claude_tools/`) still work but are deprecated. 

**Use the new tools instead:**

### Old (Deprecated)
```python
from invest.claude_tools.screening_tools import systematic_screen
```

### New (Recommended)
```python
from invest.ai_tools.claude.screening_tools import systematic_screen
```

## Benefits of New Structure

- ✅ **Consistent between Claude and Gemini**
- ✅ **Shared core business logic (no code duplication)**  
- ✅ **Better organized and maintainable**
- ✅ **Same functionality, improved architecture**

## Timeline

- **Now**: Both old and new tools work
- **Future**: Old tools may be removed in a future update

**Recommendation**: Update any scripts or code to use the new `ai_tools/claude/` imports.