# News Town - Quick Start Guide

## Prerequisites

- Python 3.12+
- PostgreSQL 16+
- API keys for OpenAI and Anthropic

## Installation

### 1. Clone and Setup

```bash
cd /Users/mterenzi/newstown
python setup.py
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```bash
DATABASE_URL=postgresql://localhost/newstown
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Create Database

```bash
createdb newstown
# OR
psql -c "CREATE DATABASE newstown;"
```

### 4. Run Migrations

```bash
source venv/bin/activate  # or venv\Scripts\activate on Windows
python -m db.migrate
```

### 5. Start News Town

```bash
python main.py
```

## What Happens Next

News Town will start running with:

1. **1 Chief** - Orchestrates all work
2. **1 Scout** - Monitors RSS feeds (Hacker News, Techmeme)
3. **2 Reporters** - Research and write articles

The system will:
- Continuously scan RSS feeds for newsworthy content
- Score each detected story
- Create tasks for stories that meet the threshold
- Automatically research and draft articles
- Log all activity in the database

## Monitoring

Watch the console output to see:
- Stories being detected
- Tasks being created
- Agents claiming and completing work
- Events being logged

## Database Inspection

```bash
psql newstown

-- See recent events
SELECT * FROM story_events ORDER BY created_at DESC LIMIT 10;

-- See active tasks
SELECT * FROM story_tasks WHERE status = 'pending' ORDER BY priority DESC;

-- See agent status
SELECT * FROM agents ORDER BY last_heartbeat DESC;

-- See detected stories
SELECT story_id, first_seen, current_stage FROM stories ORDER BY first_seen DESC;
```

## Testing

```bash
pytest tests/
```

## Next Steps

This is the MVP foundation. To extend:

1. **Add Editor agents** for quality improvement
2. **Add Publisher agents** to output final articles
3. **Add governance rules** for fact-checking
4. **Create dashboard** for human oversight
5. **Scale feed sources** beyond RSS

## Troubleshooting

**Database connection errors:**
- Ensure PostgreSQL is running
- Check DATABASE_URL in .env
- Verify database exists

**Import errors:**
- Activate virtual environment
- Run `pip install -r requirements.txt`

**API errors:**
- Verify API keys in .env
- Check API quotas/limits

## Architecture

See `implementation_plan.md` for full architecture details.
