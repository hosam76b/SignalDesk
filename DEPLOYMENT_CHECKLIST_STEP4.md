# Step 4 Deployment Checklist

**Last Updated:** 2026-08-21  
**Status:** Ready for Deployment

---

## Pre-Deployment (5 min)

- [ ] **Get Gemini API Key**
  - Visit: https://makersuite.google.com/app/apikey
  - Sign in with Google account
  - Click "Create API Key"
  - Copy the key

- [ ] **Update .env file**
  - Open: `c:\Users\HCC_HosamBheri\Desktop\facebook-monitor\.env`
  - Add line: `GEMINI_API_KEY=your_key_here`
  - Replace `your_key_here` with actual key
  - Save file

- [ ] **Install dependencies** (if needed)
  ```bash
  pip install -r requirements.txt
  ```
  Note: `google-genai==0.3.0` is already in requirements.txt

---

## Deployment (2 min)

- [ ] **Stop current FastAPI server** (if running)
  - Ctrl+C in terminal

- [ ] **Restart FastAPI server**
  ```bash
  cd c:\Users\HCC_HosamBheri\Desktop\facebook-monitor
  python -m uvicorn main:app --reload
  ```

- [ ] **Verify startup logs**
  - Look for: `✅ Gemini API client initialized` (if key is set)
  - Or: `⚠️ GEMINI_API_KEY not configured` (will use defaults)

---

## Post-Deployment Verification (10 min)

- [ ] **Open Swagger UI**
  - URL: http://localhost:8000/docs
  - Should load without errors

- [ ] **Verify new endpoints appear**
  - Look for section: "AI Analysis"
  - Should show 3 endpoints:
    - POST /api/ai/analyze-pending
    - GET /api/ai/flagged-posts
    - GET /api/ai/statistics

- [ ] **Test authentication**
  - Click "Authorize" button
  - Enter admin token from login
  - Should succeed

- [ ] **Verify database connection**
  - Check logs for: `✅ Gemini API client initialized`
  - Or error messages about database

---

## Data Preparation (5 min)

- [ ] **Ensure posts exist in database**
  
  Option A - Run scraper:
  ```bash
  POST /api/scraper/trigger
  Authorization: Bearer <admin_token>
  ```
  Wait for completion, should see posts created

  Option B - Insert test posts:
  ```sql
  -- Connect to PostgreSQL database
  INSERT INTO posts (
    source_id, external_id, platform, author, 
    content, post_url, published_at, scraped_at
  ) VALUES (
    1, 'test_001', 'test', 'Test User',
    'This is a test post that might contain violence',
    'http://example.com/post1',
    NOW(), NOW()
  );
  ```

- [ ] **Verify posts are unanalyzed**
  ```sql
  SELECT id, platform, author, ai_summary, severity_level 
  FROM posts 
  WHERE ai_summary IS NULL 
  LIMIT 5;
  ```
  Should return rows with NULL values

---

## Functional Testing (15 min)

### Test 1: Trigger Analysis
- [ ] Open Swagger: http://localhost:8000/docs
- [ ] Navigate to: **POST /api/ai/analyze-pending**
- [ ] Click "Try it out"
- [ ] Click "Execute"
- [ ] Expected response: 200 OK with statistics
- [ ] Check response includes:
  - `total_posts` > 0
  - `analyzed` > 0
  - `updated` > 0
  - `severity_breakdown` with counts

### Test 2: View Flagged Posts
- [ ] Navigate to: **GET /api/ai/flagged-posts**
- [ ] Click "Try it out"
- [ ] Set `severity` to "high" (optional)
- [ ] Set `limit` to 10
- [ ] Click "Execute"
- [ ] Expected response: 200 OK with posts array
- [ ] Check response includes posts with:
  - `severity_level` (high/critical if filtered)
  - `violence_category` (if detected)
  - `ai_summary` (Arabic text)
  - `is_flagged` = true

### Test 3: View Statistics
- [ ] Navigate to: **GET /api/ai/statistics**
- [ ] Click "Try it out"
- [ ] Click "Execute"
- [ ] Expected response: 200 OK with statistics
- [ ] Check response includes:
  - `total_posts` > 0
  - `flagged_posts` >= 0
  - `by_severity` breakdown
  - `by_platform` breakdown (if multiple platforms)
  - `by_violence_category` breakdown

---

## Access Control Testing (10 min)

### Test 4: Admin-Only Access
- [ ] Login as non-admin user (if available)
- [ ] Try: **POST /api/ai/analyze-pending**
- [ ] Expected: 403 Forbidden error

### Test 5: Authentication Required
- [ ] Remove authorization token
- [ ] Try any AI endpoint
- [ ] Expected: 401 Unauthorized or 403 Forbidden

### Test 6: Valid Admin Token
- [ ] Login as admin (admin@example.com / admin123)
- [ ] Copy token from response
- [ ] Use token in "Authorize" button
- [ ] Try: **POST /api/ai/analyze-pending**
- [ ] Expected: 200 OK with analysis results

---

## Database Verification (5 min)

- [ ] **Check Post records were updated**
  ```sql
  SELECT id, platform, author, 
         severity_level, violence_category, 
         ai_summary, is_flagged
  FROM posts 
  WHERE ai_summary IS NOT NULL 
  LIMIT 10;
  ```
  Should show analysis results

- [ ] **Count flagged posts**
  ```sql
  SELECT severity_level, COUNT(*) 
  FROM posts 
  WHERE is_flagged = true 
  GROUP BY severity_level;
  ```
  Should show breakdown by severity

- [ ] **Verify all fields populated**
  ```sql
  SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN severity_level IS NOT NULL THEN 1 ELSE 0 END) as with_severity,
    SUM(CASE WHEN ai_summary IS NOT NULL THEN 1 ELSE 0 END) as with_summary,
    SUM(CASE WHEN is_flagged THEN 1 ELSE 0 END) as flagged
  FROM posts;
  ```
  All should be equal (or nearly equal)

---

## Monitoring Setup (5 min)

- [ ] **Check application logs**
  - Look for successful analysis messages:
    - `✅ Analyzed: high | Flagged: true`
  - Check for errors:
    - `❌ Error analyzing...`
    - API initialization issues

- [ ] **Set up monitoring alerts** (optional)
  - Monitor `/api/ai/health` endpoint
  - Track response times
  - Alert on 500 errors

---

## Performance Baseline (10 min)

- [ ] **Measure single post analysis time**
  - Create 1 test post
  - Trigger analysis
  - Time the operation
  - Should take: 2-3 seconds

- [ ] **Measure batch performance**
  - Create 10 test posts
  - Trigger analysis
  - Time the operation
  - Should take: 20-30 seconds
  - (Average: 2-3 sec per post)

---

## Troubleshooting

### Issue: "GEMINI_API_KEY not configured"
**Solution:**
1. Open .env file
2. Add: `GEMINI_API_KEY=your_actual_key`
3. Restart server
4. Verify in logs

### Issue: "No unanalyzed posts found"
**Solution:**
1. Run scraper first: `POST /api/scraper/trigger`
2. Or insert test posts manually
3. Verify posts exist: `SELECT COUNT(*) FROM posts;`

### Issue: "Analysis is very slow"
**Solution:**
- Normal - Gemini API takes 2-3 seconds per post
- Batch of 50 posts = ~100-150 seconds
- Not a bug

### Issue: "403 Forbidden on analyze-pending"
**Solution:**
1. Verify using admin token (not regular user)
2. Check User.role = 'admin' in database
3. Verify authentication with /api/auth/me

### Issue: "Empty response from analyze-pending"
**Solution:**
1. Check logs for errors
2. Verify database connection
3. Ensure posts exist in database
4. Check GEMINI_API_KEY is set

### Issue: "Connection refused"
**Solution:**
1. Verify FastAPI server is running
2. Check port 8000 is not in use
3. Verify PostgreSQL database is running

---

## Rollback Plan (if needed)

If you need to revert Step 4:

1. **Remove new files:**
   ```bash
   rm app/services/ai_service.py
   rm app/services/ai_orchestrator.py
   rm app/api/ai_analysis.py
   ```

2. **Restore main.py:**
   ```python
   # Remove these lines:
   from app.api import ai_analysis as ai_routes
   app.include_router(ai_routes.router)
   ```

3. **Restart server**

Note: Analysis results in database are preserved

---

## Success Criteria

✅ **Deployment successful if:**
1. FastAPI server starts without errors
2. Swagger UI loads with /api/ai endpoints
3. POST /api/ai/analyze-pending works with admin token
4. Posts get analyzed and marked with severity_level
5. GET /api/ai/flagged-posts returns results
6. Database posts table has updated ai_summary, severity_level, violence_category

---

## Sign-Off

- [ ] **Pre-deployment checks complete**
- [ ] **GEMINI_API_KEY set in .env**
- [ ] **Server restarted**
- [ ] **Endpoints verified in Swagger**
- [ ] **Analysis trigger tested**
- [ ] **Results verified in database**
- [ ] **Performance baseline measured**
- [ ] **Documentation reviewed**

**Deployment Date:** _________________  
**Deployed By:** _________________  
**Status:** ✅ Production Ready

---

## Post-Deployment Notes

Use this space to document any observations:

```
- Analysis quality: _______________
- Performance observations: _______________
- Issues encountered: _______________
- Optimization opportunities: _______________
```

---

**For detailed information, see:** [STEP4_COMPLETION.md](STEP4_COMPLETION.md)
