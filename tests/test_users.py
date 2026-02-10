import pytest
from db.users import user_store
from api.auth import verify_password

@pytest.mark.asyncio
async def test_create_user(db):
    username = "new_user"
    password = "password123"
    role = "reporter"
    
    user_id = await user_store.create_user(username, password, role)
    assert user_id is not None
    
    user = await user_store.get_user_by_username(username)
    assert user["username"] == username
    assert user["role"] == role
    assert verify_password(password, user["password_hash"]) is True

@pytest.mark.asyncio
async def test_duplicate_username(db):
    await user_store.create_user("duplicate", "pass1")
    
    # This should raise a UniqueViolation but asyncpg usually wraps it
    with pytest.raises(Exception):
        await user_store.create_user("duplicate", "pass2")

@pytest.mark.asyncio
async def test_get_nonexistent_user(db):
    user = await user_store.get_user_by_username("nobody")
    assert user is None

@pytest.mark.asyncio
async def test_ensure_admin_exists(db):
    # First call should create
    created = await user_store.ensure_admin_exists("boss", "secret123")
    assert created is True
    
    user = await user_store.get_user_by_username("boss")
    assert user is not None
    assert user["role"] == "admin"
    
    # Second call should do nothing
    created_again = await user_store.ensure_admin_exists("boss", "different_pass")
    assert created_again is False
    
    # Verify password is NOT changed
    user_refreshed = await user_store.get_user_by_username("boss")
    assert verify_password("secret123", user_refreshed["password_hash"]) is True
