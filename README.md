# News Town

An agentic newsroom OS where AI agents collaboratively discover, investigate, verify, write, and publish news with minimal human oversight.

## Features

🤖 **Autonomous News Discovery** - Scout agents monitor RSS feeds and detect emerging stories  
📝 **Multi-Agent Writing** - Reporter and Editor agents collaborate on fact-checked articles  
📰 **Multi-Channel Publishing** - Automated distribution via RSS, Email (SendGrid), and API  
⚖️ **Governance Engine** - Rule-based oversight with approval workflows  
🔍 **Source Verification** - Minimum source requirements and fact-checking  
📊 **Full Audit Trail** - Complete event logging for accountability  
🐳 **Dockerized Deployment** - Production-ready containers with PostgreSQL

## Architecture

- **Event-sourced**: Full audit trail via immutable event log
- **Agent-native**: Specialized autonomous workers coordinated by a Chief
- **Skeptical by default**: Built-in verification and governance
- **Simple stack**: Python + PostgreSQL + pgvector

## Quick Start

### Docker (Recommended)

```bash
# Clone repository
git clone git@github.com:librenews/newstown.git
cd newstown

# Copy environment file
cp .env.example .env
# Edit .env and add your API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY)

# Start with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f app

# Access RSS feed
curl http://localhost:8000/api/feed.rss

# Stop
docker-compose down
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Set up PostgreSQL database
createdb newstown
python -m db.migrate

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run the newsroom
python main.py

# In another terminal, run the API server
python run_api.py
```

## API Endpoints

### Publishing
- `POST /api/articles/{id}/publish` - Publish article immediately
- `POST /api/articles/{id}/schedule` - Schedule for later
- `GET /api/publications` - List all publications
- `DELETE /api/publications/{id}` - Retract publication
- `GET /api/feed.rss` - RSS 2.0 feed

### Governance
- `POST /api/governance/evaluate/{id}` - Evaluate article against rules
- `GET /api/approvals/pending` - List pending approvals
- `POST /api/approvals/{id}/approve` - Approve article
- `POST /api/approvals/{id}/reject` - Reject article
- `GET /api/audit/log` - View audit log
- `GET /api/governance/rules` - List governance rules

## Environment Variables

Required:
```bash
OPENAI_API_KEY=sk-...           # For article generation
ANTHROPIC_API_KEY=sk-ant-...    # For content analysis
DATABASE_URL=postgresql://...    # PostgreSQL connection
```

Optional:
```bash
SENDGRID_API_KEY=SG...          # For email publishing
EMAIL_FROM_ADDRESS=news@...     # From address
EMAIL_FROM_NAME="News Town"     # From name
```

## Project Structure

```
newstown/
├── agents/          # Agent implementations (Scout, Reporter, Editor, Publisher)
├── chief/           # Central orchestrator
├── db/              # Database models and stores
├── governance/      # Rules engine and policy enforcement
├── publishing/      # RSS, Email publishers & scheduler
├── api/             # FastAPI REST endpoints
├── ingestion/       # Feed monitoring and story detection
├── config/          # Configuration and logging
└── tests/           # Test suite
```

## Documentation

- [Quick Start Guide](QUICKSTART.md) - Detailed setup instructions
- [Phase 3 Notes](PHASE3_NOTES.md) - Publishing system details
- [Phase 3 Quick Start](PHASE3_QUICKSTART.md) - API usage guide
- [Docker Deployment](DOCKER_DEPLOY.md) - Production deployment
- [QA Checklist](QA_CHECKLIST.md) - Testing and validation

## Development Status

✅ **Phase 1 - Core Infrastructure** (Complete)
- Multi-agent architecture
- Event-sourced design
- Task orchestration
- PostgreSQL + pgvector

✅ **Phase 2 - Human Oversight** (Complete)
- Human intervention system
- Approval workflows
- Source injection

✅ **Phase 3 - Publishing & Governance** (Complete)
- RSS + Email publishing
- Governance engine
- Background scheduler
- FastAPI REST API
- Audit logging

🚧 **Phase 4 - Enhanced Intelligence** (Planned)
- Advanced Editor agent
- Web dashboard
- Analytics
- Social media integration

## Testing

```bash
# Run all tests
docker-compose exec app pytest

# Run Phase 3 end-to-end test
docker-compose exec app python test_phase3.py

# Run with coverage
docker-compose exec app pytest --cov=. --cov-report=html
```

## Contributing

This is an early-stage project. Contributions welcome!

## License

MIT

## Links

- Repository: https://github.com/librenews/newstown
- Issues: https://github.com/librenews/newstown/issues
