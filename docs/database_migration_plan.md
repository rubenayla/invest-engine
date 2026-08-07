# Database Migration Plan

## Current State Analysis

### Existing Architecture
- **Local Dashboard**: File-based JSON storage (`dashboard_data.json`)
- **Current Size**: 3.7MB for ~415 stocks (~9.1KB per stock)
- **Projected Size**: ~24MB for all NYSE stocks (2,662 tickers)
- **Storage Format**: JSON files with dashboard data manager abstraction layer

### Why Migration is Being Considered
1. **Scale Growth**: NYSE coverage brings us to 24MB+ 
2. **User Features**: Tagging system (favorites, watchlists, notes)
3. **Web Application**: Multi-user access without authentication complexity
4. **Query Complexity**: Tag filtering and stock searches

## Migration Options Evaluated

### Option 1: Enhanced JSON (Current Recommendation)
**Use Case**: Continue local development, single-user scenarios

**Pros**:
- Zero setup complexity
- Easy backup/restore (copy files)
- Version control friendly
- Low corruption risk
- Current caching system works
- 24MB still manageable for single user

**Cons**:
- Limited querying capabilities
- Memory usage scales linearly
- No concurrent user support
- Complex tag filtering logic

**Implementation**:
```json
{
  "stocks": { /* existing valuation data */ },
  "tags": {
    "AAPL": {
      "tags": ["favorite", "growth"],
      "notes": "Strong execution",
      "created": "2025-08-21T10:00:00Z"
    }
  },
  "tag_index": {
    "favorite": ["AAPL", "MSFT"],
    "discard": ["BABA", "NIO"],
    "china-risk": ["BABA", "NIO", "PDD"]
  }
}
```

### Option 2: SQLite (NOT Recommended)
**Rejected due to**:
- Corruption risk (user had bad experience)
- Power failure vulnerability
- File locking issues
- Limited concurrent access

### Option 3: PostgreSQL for Web App (Future)
**Use Case**: Traditional multi-user web application with server-side auth

**Pros**:
- ACID transactions
- Excellent performance at scale
- Rich querying capabilities
- Battle-tested reliability

**Cons**:
- Authentication complexity
- Server management overhead
- Privacy concerns (user data on server)
- Deployment complexity

**Schema Overview**:
```sql
-- Users and authentication
users (id, email, username, password_hash, subscription_tier)

-- Shared stock data
stocks (ticker, company_name, sector, current_price, market_cap)
valuations (ticker, model_name, fair_value, margin_of_safety, model_data)

-- User-specific data  
user_stock_tags (user_id, ticker, tag, note, created_at)
user_portfolios (user_id, name, description, is_public)
portfolio_stocks (portfolio_id, ticker, weight)
```

## Recommended Architecture: Offline-First Web App

### Core Concept
**Separation of Concerns**:
- **Server**: Heavy computation (valuations, stock data) - stateless, no auth
- **Client**: Personal data (tags, favorites, notes) - stored locally
- **No authentication complexity**
- **Privacy by design** - user data never leaves their device

### Client-Side Storage: IndexedDB

**Why IndexedDB**:
- Large storage limit (~1GB typical)
- Structured data with indexes
- Transactional integrity
- Asynchronous operations
- Universal modern browser support

**Client-Side Schema**:
```javascript
const stores = {
  userTags: {
    keyPath: 'id',
    indexes: ['ticker', 'tag', 'created_at']
  },
  userNotes: {
    keyPath: 'ticker'
  },
  userPreferences: {
    keyPath: 'setting'
  },
  cachedValuations: {
    keyPath: ['ticker', 'model'],
    indexes: ['ticker', 'updated_at']
  }
};
```

### Server-Side: Simple Read-Only API

**PostgreSQL for Valuation Data Only**:
- Stocks table (ticker, company info, current price)
- Valuations table (ticker, model results, calculated_at)
- No user tables or authentication

**API Endpoints**:
```
GET /api/stocks/{ticker}/valuations
GET /api/stocks/search?sector=tech&min_margin=0.2  
GET /api/universe/nyse
GET /api/universe/sp500
```

### Architecture Diagram

```
┌─────────────────┐    ┌─────────────────┐
│   Web Frontend  │    │  Your Server    │
│                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ IndexedDB   │ │    │ │ PostgreSQL  │ │
│ │             │ │    │ │             │ │
│ │ - Tags      │ │    │ │ - Stocks    │ │
│ │ - Notes     │ │◄──►│ │ - Valuations│ │
│ │ - Favorites │ │    │ │ - Prices    │ │
│ │ - Settings  │ │    │ │             │ │
│ └─────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └─────────────────┘
```

### Technology Stack

**Frontend**:
- **React/Vue** - UI framework
- **Dexie.js** - IndexedDB wrapper library
- **Workbox** - Offline caching and PWA features
- **Tailwind CSS** - Styling

**Backend**:
- **FastAPI** - Simple REST API server
- **PostgreSQL** - Valuation data storage
- **Your existing valuation engine** - Computation logic
- **Background jobs** - Periodic valuation updates

### Data Flow

1. **Initial Load**: Client fetches fresh valuations from server API
2. **User Interactions**: Tags, notes, favorites stored in local IndexedDB
3. **Offline Mode**: App works with cached valuations + local preferences
4. **Data Portability**: Export/import functionality for user data backup
5. **Server Updates**: Periodic background updates of valuation data

### Benefits of Offline-First Approach

✅ **No Authentication Complexity**: Just public API for valuation data  
✅ **User Privacy**: Personal data stays on user's device  
✅ **Offline-First**: Works without internet connection  
✅ **Scalable**: Server only serves computational results  
✅ **Simple Deployment**: Static frontend + stateless API  
✅ **Data Portability**: Users own and control their data  
✅ **Development Speed**: No user management, sessions, etc.  
✅ **Compliance**: No GDPR/privacy concerns with user data  

## Migration Timeline & Decision Points

### Phase 1: Current Development (Now)
- **Continue with JSON** for local dashboard
- **Implement smart tagging** with JSON indexing
- **Keep existing caching and data management**

### Phase 2: Web App Preparation (Future)
- **Set up PostgreSQL** for valuation data only
- **Create FastAPI** read-only endpoints  
- **Test with existing data migration**

### Phase 3: Frontend Development (Future)
- **React/Vue frontend** with IndexedDB storage
- **Implement offline-first design patterns**
- **Progressive Web App** features

### Phase 4: Production Deployment (Future)
- **Static site hosting** (Netlify, Vercel)
- **API server deployment** (Docker, cloud services)
- **CDN setup** for global performance

## Key Decision Triggers

**Stick with JSON When**:
- Single-user local development continues
- File size remains under 50MB
- No web application requirements

**Migrate to Offline-First Web App When**:
- Want to share tool publicly  
- Need complex tag filtering and searches
- File performance becomes noticeable
- Want mobile/tablet access

**Consider Traditional Database When**:
- Need user collaboration features
- Want real-time data sharing between users
- Require complex user management
- Building enterprise features

## Technical Implementation Notes

### Data Migration Strategy
1. **Export existing JSON** to SQL schema
2. **Keep JSON as backup** during transition
3. **Gradual feature migration** (valuations first, then UI)
4. **Parallel systems** during development phase

### IndexedDB Implementation Libraries
- **Dexie.js**: Most popular IndexedDB wrapper
- **idb**: Minimalist promise-based wrapper
- **LocalForage**: Automatic fallback to localStorage

### Performance Considerations
- **Client-side caching** strategy for valuation data
- **Background sync** for offline-to-online transitions  
- **Efficient data structures** for tag filtering
- **Lazy loading** for large stock universes

### Backup and Data Portability
- **JSON export** functionality for user data
- **Import from backup** files
- **Sync across devices** via manual file transfer
- **Future**: Optional cloud backup without authentication

## Summary

The offline-first web application architecture provides the best balance of simplicity, scalability, and user control. It eliminates authentication complexity while enabling powerful multi-user scenarios through client-side data storage.

This approach maintains the tool's current simplicity while opening up web deployment possibilities and advanced user features like tagging and portfolio management.