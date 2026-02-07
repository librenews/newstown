# Phase 3: Publishing & Governance - Quick Start

## What Was Built

Phase 3 adds **publishing infrastructure** and **governance controls** to News Town.

### Publishing System

**Channels:**
- RSS 2.0 feeds
- Email newsletters (SendGrid)
- Scheduled publishing

**Components:**
- `publishing/` - Publisher implementations
- `api/publishing.py` - REST API for publishing
- `publishing/scheduler.py` - Background scheduler

### Governance System

**Features:**
- Rule-based evaluation
- Human approval workflows
- Audit logging
- Content safety checks

**Components:**
- `governance/` - Governance engine
- `api/governance.py` - REST API for governance
- `db/governance.py` - Data models

---

## Setup

### 1. Add Dependencies

```bash
pip install -r requirements.txt
```

New dependencies:
- `feedgen` - RSS generation
- `sendgrid` - Email delivery
- `fastapi` - REST API
- `uvicorn` - ASGI server

### 2. Configure SendGrid (Optional)

For email publishing:

```bash
# Get API key from sendgrid.com
export SENDGRID_API_KEY=SG.your-key-here
export EMAIL_FROM_ADDRESS=news@yourdomain.com
export EMAIL_FROM_NAME="News Town"
```

### 3. Initialize Governance Rules

```bash
python -m governance.default_rules
```

Creates 4 default rules:
- Minimum source requirement (2+ sources)
- Sensitive topic approval
- Topic restrictions
- Content moderation

---

## Usage

### Start the API Server

```bash
python run_api.py
```

Visit http://localhost:8000/docs for interactive API documentation.

### Publish an Article

**Via API:**
```bash
curl -X POST http://localhost:8000/api/articles/{article_id}/publish \
  -H "Content-Type: application/json" \
  -d '{"channels": ["rss"]}'
```

**Response:**
```json
{
  "article_id": "...",
  "channels": ["rss"],
  "results": {
    "rss": {
      "success": true,
      "publication_id": "..."
    }
  },
  "success_count": 1
}
```

### Schedule Publication

```bash
curl -X POST http://localhost:8000/api/articles/{article_id}/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "channels": ["rss"],
    "scheduled_for": "2026-02-08T06:00:00Z"
  }'
```

Scheduler will auto-publish at specified time.

### Get RSS Feed

```bash
curl http://localhost:8000/api/feed.rss
```

Returns RSS 2.0 XML.

### Governance

**Evaluate Article:**
```bash
curl -X POST http://localhost:8000/api/governance/evaluate/{article_id}
```

**Get Pending Approvals:**
```bash
curl http://localhost:8000/api/approvals/pending
```

**Approve Article:**
```bash
curl -X POST http://localhost:8000/api/approvals/{approval_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"reviewed_by": "editor@example.com", "notes": "Looks good"}'
```

---

## Testing

### End-to-End Test

```bash
python test_phase3.py
```

Tests:
- Article creation
- Governance evaluation
- RSS publishing
- Feed generation
- Retraction

---

## Architecture

```
Article Created
    ↓
Governance Evaluation
    ↓
Passed? → Publish
    ↓
Blocked? → Reject
    ↓
Requires Approval? → Approval Queue
    ↓
Human Reviews → Approve/Reject
    ↓
Approved? → Publish
```

---

## Next Steps (Phase 4)

- **Editor agent** - Quality improvement
- **Web dashboard** - Human oversight UI
- **Enhanced intelligence** - Better research
- **spaCy fix** - Entity extraction

See `phase4_roadmap.md` for details.
