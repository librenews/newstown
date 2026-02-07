# Manual Testing Guide

## Database Access

The correct database user is `newstown` (not `newsroom`):

```bash
# Connect to database
docker-compose exec db psql -U newstown -d newstown
```

### Useful Queries

```sql
-- See all tables
\dt

-- Count stories discovered
SELECT COUNT(*) as story_count FROM stories;

-- View recent stories (note: column is 'url' not 'title')
SELECT id, url, status, detected_at 
FROM stories 
ORDER BY detected_at DESC 
LIMIT 10;

-- View articles published
SELECT id, headline, byline, published_at 
FROM articles 
ORDER BY published_at DESC 
LIMIT 5;

-- View publications (RSS, Email, etc)
SELECT p.id, p.channel, p.published_at, a.headline
FROM publications p
JOIN articles a ON p.article_id = a.id
ORDER BY p.published_at DESC
LIMIT 10;

-- Check governance rules
SELECT id, rule_type, enabled, priority 
FROM governance_rules
ORDER BY priority;

-- Check audit log
SELECT event_type, severity, timestamp 
FROM audit_log 
ORDER BY timestamp DESC 
LIMIT 10;

-- Exit
\q
```

## API Testing

Start the API server (if not already running):

```bash
# Start in background
docker-compose exec -d app python run_api.py

# Or in foreground to see logs
docker-compose exec app python run_api.py
```

### API Endpoints

```bash
# Get RSS feed
curl http://localhost:8000/api/feed.rss

# List all publications
curl http://localhost:8000/api/publications | jq

# Get governance rules
curl http://localhost:8000/api/governance/rules | jq

# Check pending approvals
curl http://localhost:8000/api/approvals/pending | jq

# Publish an article (replace ARTICLE_ID)
curl -X POST http://localhost:8000/api/articles/ARTICLE_ID/publish

# View audit log
curl http://localhost:8000/api/audit/log | jq
```

## Monitor Newsroom Activity

```bash
# Watch all logs
docker-compose logs -f app

# Filter for important events
docker-compose logs -f app | grep -E "(Article published|Draft|Research completed)"

# See errors only
docker-compose logs app | grep -i error
```

## Run Tests

```bash
# Phase 3 end-to-end test
docker-compose exec app python test_phase3.py

# Python unittest (if available)
docker-compose exec app pytest

# Check container health
docker-compose ps
```

## Database Stats Quick Check

```bash
# One-liner to see counts
docker-compose exec db psql -U newstown -d newstown -c "
  SELECT 
    (SELECT COUNT(*) FROM stories) as stories,
    (SELECT COUNT(*) FROM articles) as articles,
    (SELECT COUNT(*) FROM publications) as publications,
    (SELECT COUNT(*) FROM governance_rules) as rules;"
```
