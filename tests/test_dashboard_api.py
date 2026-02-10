import pytest
import httpx
from api.app import app
from api.auth import create_access_token

@pytest.fixture
def auth_headers():
    """Valid auth token for tests."""
    token = create_access_token({"sub": "admin", "role": "admin"})
    return {"Cookie": f"access_token=Bearer {token}"}

@pytest.mark.asyncio
async def test_dashboard_root_unauthorized():
    """Verify dashboard requires login."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/dashboard/")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_dashboard_api_stats_unauthorized():
    """Verify API requires login."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/dashboard/api/stats")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_dashboard_api_stats_authorized(auth_headers):
    """Verify stats API with valid token."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/dashboard/api/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "stats" in data
    assert "total_articles" in data["stats"]
    assert "active_pipelines" in data["stats"]

@pytest.mark.asyncio
async def test_dashboard_api_stories_authorized(auth_headers):
    """Verify stories API."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/dashboard/api/stories", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_dashboard_api_prompts_authorized(auth_headers):
    """Verify prompts API."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/dashboard/api/prompts", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_dashboard_api_sources_authorized(auth_headers):
    """Verify sources API."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/dashboard/api/sources", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_health_check():
    """Public health check."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
