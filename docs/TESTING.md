# Testing Coverage Analysis

## Current State (Before Enhancement)

### Existing Tests
- **test_core.py** (6 tests) - Basic model validation
- **test_research.py** (5 tests) - Entity extraction models

### Coverage Gaps ⚠️
- ❌ No database integration tests
- ❌ No agent behavior tests
- ❌ No Chief orchestration tests
- ❌ No end-to-end workflow tests
- ❌ No search integration tests
- ❌ No error handling tests
- ❌ No concurrent task claiming tests

**Estimated Coverage: ~15%**

---

## Enhanced Test Suite

### 1. Database Tests (`test_database.py`)
**Coverage: Event sourcing, tasks, connections**

✅ Event store operations
✅ Task queue (create, claim, complete, fail)
✅ Concurrent task claiming (race conditions)
✅ Database connection pooling
✅ Transaction handling

### 2. Agent Tests (`test_agents.py`)
**Coverage: Agent lifecycle, task processing**

✅ Agent registration
✅ Heartbeat system
✅ Task claiming by role
✅ Error handling during task processing
✅ Agent shutdown

### 3. Chief Tests (`test_chief.py`)
**Coverage: Orchestration logic**

✅ Detection processing
✅ Pipeline creation
✅ Story advancement (research → draft)
✅ Stalled task recovery

### 4. Scout Tests (`test_scout.py`)
**Coverage: Feed monitoring, story detection**

✅ RSS feed parsing
✅ Newsworthiness scoring
✅ Story event creation

### 5. Reporter Tests (`test_reporter.py`)
**Coverage: Research and drafting**

✅ Research with search (mocked)
✅ Entity extraction integration
✅ Multi-source verification
✅ Draft generation (mocked LLM)

### 6. Integration Tests (`test_integration.py`)
**Coverage: End-to-end workflows**

✅ Complete story lifecycle (detect → research → draft)
✅ Multi-agent coordination
✅ Chief + Reporter interaction

### 7. Search Tests (`test_search.py`)
**Coverage: Search providers**

✅ Search result parsing (mocked)
✅ Multiple provider support
✅ Error handling

---

## Test Infrastructure

### Fixtures (`conftest.py`)
- Database setup/teardown
- Test database with clean state
- Mock LLM responses
- Sample events and tasks

### Coverage Tools
- `pytest-cov` for coverage reports
- `pytest-asyncio` for async tests
- Target: **80%+ coverage**

---

## Running Tests

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=. --cov-report=html --cov-report=term

# Specific test file
pytest tests/test_database.py -v

# Fast tests only (skip integration)
pytest -m "not integration"
```

---

## CI/CD Integration

Tests run automatically on:
- Every commit
- Pull requests
- Pre-deployment

Blocks merge if:
- Tests fail
- Coverage drops below 80%
