import pytest
from fastapi.testclient import TestClient
from main import app
from db.governance import article_review_store
from agents.base import AgentRole
from uuid import uuid4

client = TestClient(app)

@pytest.mark.asyncio
async def test_dashboard_quality_api(test_user_token):
    """Test the detailed quality metrics endpoint."""
    response = client.get(
        "/dashboard/api/quality",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "rejection_rate" in data
    assert "avg_revisions" in data
    assert "trends" in data

@pytest.mark.asyncio
async def test_dashboard_performance_api(test_user_token):
    """Test the agent performance analytics endpoint."""
    response = client.get(
        "/dashboard/api/performance",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    # Should be a list of roles with success/failure counts
    assert isinstance(data, list)
    if len(data) > 0:
        assert "role" in data[0]
        assert "successes" in data[0]
        assert "failures" in data[0]

@pytest.mark.asyncio
async def test_stats_extension(test_user_token):
    """Test that main stats ahora include quality metrics."""
    response = client.get(
        "/dashboard/api/stats",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 200
    stats = response.json()["stats"]
    assert "avg_quality_score" in stats
    assert "avg_verification" in stats
    assert "avg_style" in stats
