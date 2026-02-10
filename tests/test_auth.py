import pytest
from jose import jwt
from datetime import timedelta
from api.auth import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    decode_access_token,
    SECRET_KEY,
    ALGORITHM
)

def test_password_hashing():
    password = "secret_password"
    hashed = get_password_hash(password)
    
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong_password", hashed) is False

def test_jwt_token_flow():
    data = {"sub": "testuser", "role": "admin"}
    token = create_access_token(data)
    
    # Check if token is a valid JWT
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == "testuser"
    assert decoded["role"] == "admin"
    assert "exp" in decoded

def test_decode_access_token():
    data = {"sub": "alice", "role": "viewer"}
    token = create_access_token(data)
    
    payload = decode_access_token(token)
    assert payload["sub"] == "alice"
    assert payload["role"] == "viewer"

def test_decode_invalid_token():
    assert decode_access_token("invalid.token.here") is None

def test_token_expiration():
    data = {"sub": "expiring_user"}
    # Create token that expired 1 minute ago
    token = create_access_token(data, expires_delta=timedelta(minutes=-1))
    
    payload = decode_access_token(token)
    assert payload is None
