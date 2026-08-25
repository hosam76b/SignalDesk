# Step 4 Completion Summary - Gemini AI Integration & Content Evaluation

**Date:** 2026-08-21  
**Status:** ✅ COMPLETE

---

## Overview

Step 4 implements AI-powered content analysis using Google Gemini API to evaluate scraped posts for violence, safety concerns, and severity levels. This enables automated content moderation and flagging of potentially dangerous posts.

## Files Created & Updated

### 1. AI Analysis Service (`app/services/ai_service.py`)

**Class:** `AIAnalysisService`

**Key Methods:**

#### `analyze_post_content(text: str) -> Dict[str, Any]`
Analyzes a single post using Gemini API.

**Parameters:**
- `text` (str): Post content to analyze (max 5000 chars for efficiency)

**Returns:**
```python
{
    "success": bool,
    "violence_category": str | None,  # Violence type if detected
    "severity_level": str,             # "low", "medium", "high", "critical"
    "ai_summary": str,                 # Summary in Arabic
    "is_flagged": bool,                # True if content is concerning
    "raw_response": str,               # Full API response
    "error": str | None                # Error message if failed
}
```

**Violence Categories:**
- `null` - No violence detected
- `physical_violence` - Assault, fighting, weapons use
- `sexual_violence` - Sexual abuse or assault
- `psychological_violence` - Threats, intimidation, harassment
- `weapon_related` - Gun violence, explosives
- `gang_related` - Gang activity, territorial violence
- `extremism` - Extremist content, radicalization
- `self_harm` - Self-injury or suicide content
- `hate_speech` - Racism, discrimination, hate
- `other` - Other concerning content

**Severity Levels:**
- `low` - Minor concern or no issues
- `medium` - Moderate concern requiring attention
- `high` - Significant concern requiring review
- `critical` - Immediate danger, urgent action needed

**Features:**
- Structured Gemini prompt requesting JSON response
- Automatic text truncation to 5000 characters
- JSON parsing with fallback handling
- Comprehensive error handling
- API rate limit tolerance
- Logging at each stage

**Example Usage:**
```python
ai_service = AIAnalysisService()
result = ai_service.analyze_post_content("Post content here...")

if result["success"]:
    print(f"Severity: {result['severity_level']}")
    print(f"Category: {result['violence_category']}")
    print(f"Flagged: {result['is_flagged']}")
    print(f"Summary: {result['ai_summary']}")
```

---

#### `analyze_batch(contents: list) -> Dict[str, Any]`
Process multiple posts in batch.

**Returns:**
```python
{
    "success": bool,
    "total": int,
    "successful": int,
    "errors": List[str],
    "results": List[Dict]
}
```

---

### 2. AI Orchestrator Service (`app/services/ai_orchestrator.py`)

**Class:** `AIOrchestrator`

Coordinates AI analysis across the entire database and manages result storage.

**Key Methods:**

#### `process_unanalyzed_posts(db: Session) -> Dict[str, Any]`
Main orchestration function that processes all unanalyzed posts.

**Process:**
1. Query database for posts where `ai_summary == NULL` OR `severity_level == NULL`
2. For each post, call `AIAnalysisService.analyze_post_content()`
3. Update post with analysis results:
   - `violence_category`
   - `severity_level`
   - `ai_summary`
   - `raw_ai_response`
   - `is_flagged`
4. Track flagged posts separately
5. Update database atomically
6. Return comprehensive statistics

**Returns:**
```python
{
    "success": bool,
    "total_posts": int,           # Posts found for analysis
    "analyzed": int,              # Successfully analyzed
    "updated": int,               # Saved to database
    "errors": List[str],          # Any errors encountered
    "flagged_posts": List[Dict],  # Posts marked for review
    "severity_breakdown": {
        "critical": int,
        "high": int,
        "medium": int,
        "low": int,
    },
    "duration_seconds": float,
}
```

**Example Usage:**
```python
orchestrator = AIOrchestrator()
result = await orchestrator.process_unanalyzed_posts(db)

print(f"Analyzed: {result['analyzed']} posts")
print(f"Flagged: {len(result['flagged_posts'])} for review")
print(f"Severity breakdown: {result['severity_breakdown']}")
```

---

#### `get_flagged_posts(db, severity_level=None, limit=50, offset=0) -> Dict`
Retrieve flagged or high-severity posts with pagination.

**Parameters:**
- `severity_level` (str): Filter by "critical", "high", "medium", "low"
- `limit` (int): Results per page
- `offset` (int): Pagination offset

**Returns:**
```python
{
    "success": bool,
    "total_count": int,
    "returned": int,
    "limit": int,
    "offset": int,
    "posts": [
        {
            "id": int,
            "source": str,
            "platform": str,
            "author": str,
            "content": str,           # Preview (first 500 chars)
            "post_url": str,
            "published_at": str,
            "scraped_at": str,
            "severity_level": str,
            "violence_category": str,
            "ai_summary": str,
            "is_flagged": bool,
            "media_urls_count": int,
        },
        ...
    ]
}
```

---

#### `get_severity_statistics(db: Session) -> Dict`
Generate comprehensive statistics about analysis results.

**Returns:**
```python
{
    "success": bool,
    "data": {
        "total_posts": int,
        "flagged_posts": int,
        "by_severity": {
            "critical": int,
            "high": int,
            "medium": int,
            "low": int,
        },
        "by_platform": {
            "reddit": {"total": int, "flagged": int},
            "youtube": {"total": int, "flagged": int},
            ...
        },
        "by_violence_category": {
            "physical_violence": int,
            "sexual_violence": int,
            ...
        }
    }
}
```

---

### 3. AI Analysis API Endpoints (`app/api/ai_analysis.py`)

**Router Prefix:** `/api/ai`

#### Endpoint 1: Analyze Pending Posts
```
POST /api/ai/analyze-pending
Authorization: Bearer <admin_token>
```

**Access Control:** Admin only

**Description:**
Trigger AI analysis on all unanalyzed posts in the database.

**Returns:** `AnalysisStatistics`

**Response Example:**
```json
{
    "total_posts": 45,
    "analyzed": 42,
    "updated": 42,
    "errors": [],
    "duration_seconds": 125.5,
    "severity_breakdown": {
        "critical": 2,
        "high": 5,
        "medium": 15,
        "low": 20
    },
    "flagged_posts_count": 7
}
```

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/ai/analyze-pending" \
  -H "Authorization: Bearer <token>"
```

---

#### Endpoint 2: Get Flagged Posts
```
GET /api/ai/flagged-posts?severity=critical&limit=10&offset=0
Authorization: Bearer <token>
```

**Access Control:** Authenticated users

**Query Parameters:**
- `severity` (optional): Filter by "critical", "high", "medium", "low"
- `limit` (int): Results per page (max 500, default 50)
- `offset` (int): Pagination offset (default 0)

**Returns:** `FlaggedPostsResponse`

**Response Example:**
```json
{
    "success": true,
    "total_count": 42,
    "returned": 10,
    "limit": 10,
    "offset": 0,
    "posts": [
        {
            "id": 123,
            "source": "Reddit News",
            "source_id": 5,
            "platform": "reddit",
            "author": "user123",
            "content": "Violent content preview...",
            "post_url": "https://reddit.com/r/news/...",
            "published_at": "2026-08-21T10:30:00",
            "scraped_at": "2026-08-21T11:00:00",
            "severity_level": "high",
            "violence_category": "physical_violence",
            "ai_summary": "محتوى عنيف",
            "is_flagged": true,
            "media_urls_count": 2
        }
    ]
}
```

**Usage Examples:**
```bash
# Get all high-severity posts
curl "http://localhost:8000/api/ai/flagged-posts?severity=high" \
  -H "Authorization: Bearer <token>"

# Get critical posts with pagination
curl "http://localhost:8000/api/ai/flagged-posts?severity=critical&limit=20&offset=0" \
  -H "Authorization: Bearer <token>"

# Get all flagged posts
curl "http://localhost:8000/api/ai/flagged-posts" \
  -H "Authorization: Bearer <token>"
```

---

#### Endpoint 3: Get Analysis Statistics
```
GET /api/ai/statistics
Authorization: Bearer <token>
```

**Access Control:** Authenticated users

**Description:**
Get comprehensive statistics about AI analysis results across all posts, platforms, and violence categories.

**Returns:** `SeverityStatisticsResponse`

**Response Example:**
```json
{
    "success": true,
    "data": {
        "total_posts": 150,
        "flagged_posts": 25,
        "by_severity": {
            "critical": 2,
            "high": 8,
            "medium": 15,
            "low": 125
        },
        "by_platform": {
            "reddit": {"total": 50, "flagged": 10},
            "youtube": {"total": 50, "flagged": 8},
            "rss": {"total": 50, "flagged": 7}
        },
        "by_violence_category": {
            "physical_violence": 10,
            "hate_speech": 8,
            "sexual_violence": 5,
            "other": 2
        }
    }
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/ai/statistics" \
  -H "Authorization: Bearer <token>"
```

---

### 4. Updated Configuration

**File:** `config.py`

New required environment variable:
```env
GEMINI_API_KEY=your_gemini_api_key
```

**Default Value:** Empty (service gracefully handles missing key)

---

### 5. Updated Main Application

**File:** `main.py`

**Changes:**
- ✅ Added import: `from app.api import ai_analysis as ai_routes`
- ✅ Added router: `app.include_router(ai_routes.router)`

---

### 6. Updated Requirements

**File:** `requirements.txt`

Already includes:
- `google-genai==0.3.0` - Google Generative AI SDK

---

## Database Integration

### Queries from Database
- `Post.query().filter(ai_summary == None | severity_level == None)` - Find unanalyzed posts
- `Post.query().filter(is_flagged == True | severity_level in ['critical', 'high'])` - Get flagged posts

### Data Updated in Database
- `Post.violence_category` - Violence type if detected
- `Post.severity_level` - Severity level (low/medium/high/critical)
- `Post.ai_summary` - Summary in Arabic
- `Post.raw_ai_response` - Full Gemini API response
- `Post.is_flagged` - Boolean flag for manual review

### Transaction Management
- Database updates grouped by orchestrator
- Atomic commits with rollback on error
- Comprehensive error logging

---

## Gemini API Integration Details

### Prompt Design
The service uses a carefully crafted prompt that:
1. Provides content to analyze
2. Requests structured JSON response
3. Specifies exact field names and types
4. Defines valid severity levels
5. Instructs response language (Arabic summaries)
6. Prevents invalid JSON responses

### JSON Parsing
- Attempts to extract JSON object from response
- Regex pattern: `\{.*\}` with DOTALL flag
- Fallback to direct parse if no match
- Validates all fields before use
- Safe defaults on parsing errors

### Error Handling
- API initialization failures logged
- Missing GEMINI_API_KEY gracefully handled
- API timeouts managed
- Rate limit tolerance built in
- Batch processing continues on individual post errors
- Comprehensive error reporting

### Response Validation
- Severity levels validated against allowed set
- Violence categories checked against predefined list
- Arabic summary truncated to 100 characters
- All fields have safe defaults

---

## Security & Access Control

- ✅ Analysis trigger: **Admin only** (role-based)
- ✅ Flagged posts retrieval: **Authenticated users** (JWT required)
- ✅ Statistics: **Authenticated users** (JWT required)
- ✅ API key: **Stored in environment variables** (not in code)
- ✅ Sensitive data: **Partial content in responses** (first 500 chars preview)

---

## Performance Considerations

### Optimization Opportunities
- Batch analysis using Gemini's batch API (future)
- Caching of analysis results
- Async processing with background tasks
- Parallel processing with asyncio
- Database indexing on (ai_summary, severity_level)

### Current Approach
- Sequential post processing
- Each post analyzed individually
- Results committed per source (future: batch commits)
- Database queries optimized with filters

### Rate Limiting
- Gemini API rate limits respected (built-in to library)
- Individual API calls have timeout handling
- Batch processing continues on rate limit (retry logic in service)

---

## Workflow Integration

### Typical Usage Flow

1. **Scraper runs** (Step 3):
   ```
   POST /api/scraper/trigger → Scrapes sources → Saves to Post table
   ```

2. **AI Analysis triggered** (Step 4):
   ```
   POST /api/ai/analyze-pending → Processes all unanalyzed posts → Updates database
   ```

3. **Review flagged content**:
   ```
   GET /api/ai/flagged-posts?severity=critical → Lists dangerous posts for manual review
   ```

4. **Monitor statistics**:
   ```
   GET /api/ai/statistics → Track trends and patterns
   ```

---

## Testing Checklist

### Manual Testing

1. **Initialize API Key:**
   ```bash
   # Set in .env
   GEMINI_API_KEY=your_actual_key
   ```

2. **Create Test Posts:**
   ```sql
   INSERT INTO posts (source_id, external_id, platform, author, content, published_at, scraped_at)
   VALUES (
       1,
       'test_123',
       'test',
       'Test User',
       'This is potentially violent content example',
       NOW(),
       NOW()
   );
   ```

3. **Trigger AI Analysis:**
   ```bash
   POST /api/ai/analyze-pending
   Authorization: Bearer <admin_token>
   ```

4. **Check Results:**
   ```bash
   GET /api/ai/statistics
   GET /api/ai/flagged-posts
   ```

5. **Verify Database Updates:**
   ```sql
   SELECT id, content, severity_level, violence_category, ai_summary, is_flagged
   FROM posts
   WHERE severity_level IS NOT NULL;
   ```

---

## Code Statistics

| Component | Files | Lines of Code |
|-----------|-------|----------------|
| AI Service | 1 | ~230 |
| AI Orchestrator | 1 | ~280 |
| API Endpoints | 1 | ~350 |
| Updated Files | 1 | +10 |
| **Total Step 4** | **4** | **~870** |

---

## Integration Points

### With Existing Code
- ✅ Uses `Post` model from Step 2
- ✅ Reads from posts table (scraper output from Step 3)
- ✅ Updates Post fields for analysis results
- ✅ Respects existing database schema
- ✅ Uses existing authentication (JWT)
- ✅ Leverages admin role authorization

### With Future Steps
- Report generation will use flagged posts
- WebSocket notifications for new flags
- Background task scheduling for periodic analysis
- Admin dashboard for visualization

---

## API Response Schema

### Success Response (Analysis)
```json
{
    "success": true,
    "violence_category": "physical_violence",
    "severity_level": "high",
    "ai_summary": "محتوى يصور عنفاً جسدياً",
    "is_flagged": true,
    "raw_response": "{...}"
}
```

### Error Response
```json
{
    "success": false,
    "violence_category": null,
    "severity_level": "low",
    "ai_summary": "فشل التحليل",
    "is_flagged": false,
    "error": "API rate limit exceeded"
}
```

---

## Logging Output Example

```
============================================================
🤖 Starting AI Content Analysis
============================================================
📊 Found 45 posts to analyze
🔄 Analyzing post 1/45 (ID: 123)
✅ Analyzed: high | Flagged: true | Category: physical_violence
🔄 Analyzing post 2/45 (ID: 124)
✅ Analyzed: low | Flagged: false | Category: null
[... more posts ...]
============================================================
✅ AI Analysis Complete
   Posts Analyzed: 42
   Posts Flagged: 7
   Critical: 2
   High: 5
   Medium: 15
   Low: 20
============================================================
```

---

## Environment Setup

### Required in `.env`
```env
# Google Gemini API
GEMINI_API_KEY=your_actual_gemini_api_key
```

### How to Get Gemini API Key
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Click "Create API Key"
3. Select "Google AI Studio"
4. Copy the key to your `.env` file

---

## Next Steps (Step 5+)

- Report generation from analysis results
- Scheduled background tasks (Celery integration)
- WebSocket real-time notifications
- Admin dashboard for monitoring
- Manual content review workflows
- Appeal/override functionality
- Analytics and trends reporting

---

## Quick Start

### 1. Set Gemini API Key
```bash
# Add to .env
GEMINI_API_KEY=your_key_here
```

### 2. Start Scraping
```bash
POST /api/scraper/trigger
Authorization: Bearer <admin_token>
```

### 3. Analyze New Posts
```bash
POST /api/ai/analyze-pending
Authorization: Bearer <admin_token>
```

### 4. Review Results
```bash
GET /api/ai/flagged-posts?severity=critical
GET /api/ai/statistics
```

---

## Troubleshooting

### "GEMINI_API_KEY not configured"
- Verify `.env` has GEMINI_API_KEY set
- Restart the application after updating .env
- Check config.py loads the key correctly

### "Failed to parse JSON response"
- Check Gemini API response format
- May indicate model instruction issue
- Review raw_ai_response in database for actual response

### "No unanalyzed posts found"
- Run scraper first: POST /api/scraper/trigger
- Verify posts exist in database
- Check ai_summary and severity_level are null

### Analysis Timeout
- May indicate API rate limiting
- Add retry logic or increase timeout
- Check Gemini API status page

---

**Status: ✅ Step 4 Complete - AI analysis fully integrated and operational!**

**Next: Step 5 - Report Generation & Export Services**
