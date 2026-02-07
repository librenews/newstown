# QA Checklist - News Town MVP

Test this checklist before proceeding to Phase 2. This ensures the rename (Mayor→Chief) worked and all core functionality is intact.

---

## Prerequisites

1. **Environment Setup**
   ```bash
   # Create .env file
   cp .env.example .env
   
   # Add your API keys (minimum required)
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   BRAVE_API_KEY=BSA...  # Optional but recommended
   
   # Database
   DATABASE_URL=postgresql://localhost/newstown
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```

3. **Database Setup**
   ```bash
   # Create database
   psql -c "CREATE DATABASE newstown;"
   
   # Run migrations
   python -m db.migrate
   ```

---

## QA Test Cases

### 1. Unit Tests ✓

```bash
# Run fast tests (should complete in ~3 seconds)
./run_tests.sh

# Run ALL tests including integration (~15 seconds)
./run_tests.sh all

# Generate coverage report
./run_tests.sh coverage
```

**Expected Result:**
- ✅ All tests pass
- ✅ No errors about "Mayor" (should all be "Chief" now)
- ✅ Coverage > 70%

**Check for:**
- Database connection works
- Event store appends events
- Task queue claims/completes tasks
- Chief processes detections
- Reporter handles research/draft tasks

---

### 2. Database Schema ✓

```bash
# Connect to database
psql newstown

# Verify tables exist
\dt

# Check agent role enum
SELECT DISTINCT role FROM agents;

# Check schema comment (should mention 'chief' not 'mayor')
\d+ agents
```

**Expected Result:**
- ✅ Tables: `agents`, `story_events`, `story_tasks`, `story_memory`, `stories`
- ✅ Schema comment says "Roles: chief, scout, reporter, editor, publisher"

---

### 3. Chief Rename Verification ✓

```bash
# Search for any remaining "Mayor" references
grep -r "Mayor" --include="*.py" newstown/ || echo "✅ No Mayor references found"
grep -r "MAYOR" --include="*.py" newstown/ || echo "✅ No MAYOR references found"

# Verify Chief exists
grep -r "class Chief" newstown/
```

**Expected Result:**
- ✅ No "Mayor" or "MAYOR" found in Python files
- ✅ `class Chief` found in `chief/orchestrator.py`

---

### 4. Manual System Test (End-to-End)

**Option A: Docker (Recommended)**

```bash
# Start everything
docker-compose up --build

# Watch logs for:
# - "Chief started"
# - "Scout scanning feed"
# - "Story detected"
# - "Research completed"
# - "Draft generation"
```

**Option B: Local**

```bash
# Start the system
python main.py

# Watch terminal output
```

**Monitor for 2-3 minutes and verify:**

1. **Chief Agent Starts** ✓
   ```
   ✅ "Chief started" in logs
   ✅ No errors during startup
   ```

2. **Scout Detects Stories** ✓
   ```
   ✅ "Scout scanning feed" messages
   ✅ "Story detected" events (if feeds have new content)
   ✅ Newsworthiness scores calculated
   ```

3. **Chief Creates Pipelines** ✓
   ```
   ✅ "Story pipeline created" for high-score detections
   ✅ "story.rejected" for low-score detections
   ✅ Research tasks created
   ```

4. **Reporter Researches** ✓
   ```
   ✅ "Researching story" messages
   ✅ "Entities extracted" (if spaCy installed)
   ✅ "Search completed" (if Brave API key configured)
   ✅ "Research completed" with source counts
   ```

5. **Chief Advances Pipeline** ✓
   ```
   ✅ "Draft task created" after research completes
   ```

6. **Reporter Drafts** ✓
   ```
   ✅ "Drafting article" messages
   ✅ "Draft generation" with Claude
   ✅ "Task completed successfully"
   ```

---

### 5. Database Inspection

While system is running, in another terminal:

```bash
psql newstown
```

**Check recent activity:**

```sql
-- See recent events
SELECT 
    event_type, 
    data->>'title' as title, 
    created_at 
FROM story_events 
ORDER BY created_at DESC 
LIMIT 10;

-- See agent health (should show 'chief' not 'mayor')
SELECT 
    role, 
    status, 
    last_heartbeat,
    now() - last_heartbeat as age
FROM agents 
ORDER BY last_heartbeat DESC;

-- See active/pending tasks
SELECT 
    stage, 
    status, 
    priority, 
    created_at 
FROM story_tasks 
ORDER BY created_at DESC 
LIMIT 10;

-- See complete story pipeline
SELECT 
    story_id,
    COUNT(*) as event_count,
    array_agg(DISTINCT event_type ORDER BY event_type) as events
FROM story_events 
GROUP BY story_id 
ORDER BY MAX(created_at) DESC 
LIMIT 5;
```

**Expected Results:**
- ✅ Events being logged (`story.detected`, `story.created`, `research.completed`, etc.)
- ✅ Agent role shows as `"chief"` not `"mayor"`
- ✅ Heartbeats within last 30 seconds
- ✅ Tasks moving from `pending` → `active` → `completed`

---

### 6. Search Integration Test

Only if you added `BRAVE_API_KEY` to `.env`:

```sql
-- Find a completed research task
SELECT 
    output 
FROM story_tasks 
WHERE stage = 'research' 
  AND status = 'completed' 
ORDER BY completed_at DESC 
LIMIT 1;
```

**Expected Result:**
- ✅ `output` includes:
  - `sources` array with multiple entries
  - `entities` object with people/orgs/locations
  - `verified: true` (if multiple sources found)
  - `source_count >= 2` (if corroborating sources found)

---

### 7. Entity Extraction Test

Only if you installed spaCy model:

```bash
# Quick test
python -c "
from ingestion.entities import entity_extractor
text = 'Apple Inc. CEO Tim Cook announced layoffs in San Francisco.'
entities = entity_extractor.extract(text)
for e in entities:
    print(f'{e.text} ({e.label_})')
"
```

**Expected Result:**
```
✅ Apple Inc. (ORG)
✅ Tim Cook (PERSON)
✅ San Francisco (GPE)
```

---

## Common Issues & Fixes

### Issue: Tests fail with "Mayor not found"
**Fix:** Run the sed commands above to complete the rename.

### Issue: "spaCy model not found"
**Fix:** 
```bash
python -m spacy download en_core_web_sm
```

### Issue: "ANTHROPIC_API_KEY not set"
**Fix:** Add to `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### Issue: "Database connection refused"
**Fix:** 
```bash
# Make sure PostgreSQL is running
brew services start postgresql  # macOS
sudo service postgresql start   # Linux

# Verify it's running
psql -l
```

### Issue: No stories detected
**Possible reasons:**
1. RSS feeds have no new content (normal)
2. All stories score below threshold (0.6)
3. Scout not configured with feeds

**Verify Scout is working:**
```sql
SELECT COUNT(*) FROM story_events WHERE event_type = 'story.detected';
```

If 0, wait 5 minutes (Scout scans every 5 min by default).

### Issue: Research completes but no sources found
**Possible reasons:**
1. `BRAVE_API_KEY` not configured (searches will be skipped)
2. Story title returns no search results

**Check:**
```bash
# Verify Brave API key is loaded
python -c "from config.settings import settings; print('OK' if settings.brave_api_key else 'NOT SET')"
```

---

## Success Criteria

**Before proceeding to Phase 2, confirm:**

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] No remaining "Mayor" references in code
- [ ] Chief agent starts and runs without errors
- [ ] Scout detects stories (or runs without errors if no new stories)
- [ ] Reporter completes research tasks
- [ ] Reporter drafts articles using Claude
- [ ] Database shows proper event flow
- [ ] Agent role shows as "chief" in database
- [ ] Search integration works (if API key configured)
- [ ] Entity extraction works (if spaCy installed)

---

## Quick Sanity Check (5 minutes)

If you want a fast validation:

```bash
# 1. Tests
./run_tests.sh fast

# 2. Database
psql newstown -c "SELECT role FROM agents;"  # Should show 'chief' eventually

# 3. Run for 60 seconds
timeout 60 python main.py || true

# 4. Check activity
psql newstown -c "SELECT event_type, COUNT(*) FROM story_events GROUP BY event_type;"
```

**Expected:**
- Tests pass
- System runs without crashes
- At least some events in database

---

## Ready for Phase 2?

If all checks pass, you're ready to add:
- ✨ Editor agent (quality improvement)
- ✨ Publisher agent (output articles)
- ✨ Governance rules
- ✨ Human oversight dashboard

Proceed to Phase 2 implementation!

---

# Phase 2 - Human Oversight QA

## Quick Tests

```bash
# 1. Verify Phase 2 tables exist
docker-compose exec -T db psql -U newstown -d newstown -c "\dt" | grep -E "(human_prompts|story_sources|articles)"

# 2. Run Phase 2 unit tests  
docker-compose exec app pytest tests/test_human_oversight.py tests/test_articles.py -v

# 3. Run Phase 2 integration tests
docker-compose exec app pytest tests/test_phase2_integration.py -v -m ''

# 4. Run full suite
docker-compose exec app pytest tests/ -v
```

## Expected Results

- ✅ 3 new tables: human_prompts, story_sources, articles
- ✅ 32 Phase 2 unit tests pass (15 + 17)
- ✅ 8 integration tests pass
- ✅ ~63 total tests pass

## Manual Validation

See walkthrough.md for end-to-end workflow testing.
