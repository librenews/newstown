# News Town

An agentic newsroom OS where AI agents collaboratively discover, investigate, verify, write, and publish news with minimal human oversight.

## Architecture

- **Event-sourced**: Full audit trail via immutable event log
- **Agent-native**: Specialized autonomous workers coordinated by a Chief
- **Skeptical by default**: Built-in verification and fact-checking
- **Simple stack**: Python + Postgres only

## Project Structure

```
newstown/
├── agents/          # Agent implementations (Scout, Reporter, Editor, Publisher)
├── chief/           # Central orchestrator
├── db/              # Database schema and migrations
├── governance/      # Rules engine and policy enforcement
├── ingestion/       # Feed monitoring and story detection
├── config/          # Configuration files
└── tests/           # Test suite
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up database
psql -c "CREATE DATABASE newstown;"
python -m db.migrate

# Run the system
python -m mayor.run
```

## Status

🚧 **Phase 1 - Foundation** (In Progress)

Building core infrastructure and agent framework.
